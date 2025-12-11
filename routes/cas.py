from __future__ import annotations

import json
import logging
from typing import Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from xml.etree import ElementTree

import requests
from flask import Blueprint, redirect, request, session, url_for
from sqlalchemy import select

from utils.database import User, session_scope
from utils.settings import CONFIG

cas_bp = Blueprint("cas", __name__)
logger = logging.getLogger(__name__)


def _first_attribute(
    attributes: Mapping[str, list[str]], keys: Iterable[str]
) -> str | None:
    for key in keys:
        values = attributes.get(key)
        if not values:
            continue
        return values[0]
    return None


def _safe_redirect(target: str | None) -> str | None:
    if target and target.startswith("/"):
        return target
    return None


def _append_query(url: str, params: Mapping[str, str | None]) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in params.items():
        if value is None:
            continue
        query[key] = value
    new_query = urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


def _service_url(relay_state: str | None = None) -> str:
    base = CONFIG.CAS_SERVICE_URL or url_for("cas.cas_callback", _external=True)
    if relay_state:
        return _append_query(base, {"next": relay_state})
    return base


def _parse_cas_response(payload: str) -> tuple[str | None, dict[str, list[str]], str | None]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ValueError("Invalid CAS response XML") from exc

    failure_node = root.find(".//{*}authenticationFailure")
    if failure_node is not None:
        return None, {}, (failure_node.text or "CAS authentication failed").strip()

    success_node = root.find(".//{*}authenticationSuccess")
    if success_node is None:
        return None, {}, "CAS response missing authenticationSuccess element"

    username = success_node.findtext(".//{*}user")

    attributes: dict[str, list[str]] = {}
    for child in success_node:
        tag = child.tag.split("}", 1)[-1]
        if tag == "user":
            continue
        if tag == "attributes":
            for attr_child in child:
                attr_tag = attr_child.tag.split("}", 1)[-1]
                value = (attr_child.text or "").strip()
                if value:
                    attributes.setdefault(attr_tag, []).append(value)
            continue
        value = (child.text or "").strip()
        if value:
            attributes.setdefault(tag, []).append(value)

    return username, attributes, None


@cas_bp.route("/auth/cas/login")
def cas_login():
    if not CONFIG.CAS_ENABLED:
        return "CAS authentication is disabled in this environment", 503

    relay_state = _safe_redirect(request.args.get("next"))
    service_url = _service_url(relay_state)
    login_url = f"{CONFIG.CAS_LOGIN_URL}?{urlencode({'service': service_url})}"
    return redirect(login_url)


@cas_bp.route("/auth/cas/callback")
def cas_callback():
    if not CONFIG.CAS_ENABLED:
        return "CAS authentication is disabled in this environment", 503

    ticket = request.args.get("ticket")
    relay_state = _safe_redirect(request.args.get("next"))
    if not ticket:
        return "Missing CAS ticket", 400

    service_url = _service_url(relay_state)
    try:
        response = requests.get(
            CONFIG.CAS_VALIDATE_URL,
            params={"ticket": ticket, "service": service_url},
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.error("CAS validation request failed: %s", exc)
        return "Unable to validate CAS ticket", 502

    if response.status_code != 200:
        logger.error(
            "CAS validation returned non-200 status: %s", response.status_code
        )
        return "CAS validation failed", 502

    try:
        username, attributes, failure_reason = _parse_cas_response(response.text)
    except ValueError as exc:
        logger.error("CAS validation response parse error: %s", exc)
        return "Unable to parse CAS response", 500

    if failure_reason:
        logger.warning("CAS authentication failed: %s", failure_reason)
        return f"CAS authentication failed: {failure_reason}", 401

    attribute_map = CONFIG.SSO_ATTRIBUTE_MAP
    asurite = _first_attribute(attributes, attribute_map["asurite"]) or username
    email = _first_attribute(attributes, attribute_map["email"])
    full_name = _first_attribute(attributes, attribute_map["full_name"])
    first_name = _first_attribute(attributes, attribute_map["first_name"])
    last_name = _first_attribute(attributes, attribute_map["last_name"])

    affiliations_values: list[str] = []
    for key in attribute_map["affiliations"]:
        values = attributes.get(key)
        if values:
            affiliations_values = values
            break

    if not asurite:
        logger.error(
            "CAS response missing ASURITE/network ID; available attribute keys: %s",
            sorted(attributes.keys()),
        )
        return "CAS response missing required ASURITE/network ID", 400

    if not email and asurite:
        email = f"{asurite}@asu.edu"
        logger.info("CAS response missing email; inferred %s", email)

    user_record_id: int | None = None
    is_banned = False
    with session_scope() as db_session:
        stmt = select(User).where(User.asurite_id == asurite)
        user = db_session.execute(stmt).scalar_one_or_none()

        if user is not None and user.banned:
            logger.warning("Banned ASURITE attempted verification: %s", asurite)
            is_banned = True
        else:
            if user is None:
                user = User(asurite_id=asurite, email=email or "")
                db_session.add(user)

            user.email = email or ""
            user.full_name = full_name
            user.first_name = first_name
            user.last_name = last_name
            user.affiliations = (
                ",".join(sorted(set(affiliations_values))) if affiliations_values else None
            )

            user.saml_session_index = ticket
            user.saml_attributes = json.dumps(attributes)

            db_session.flush()
            user_record_id = user.id

    if is_banned:
        session["verification_error"] = "This ASURITE is banned from verification."
        try:
            return redirect(url_for("verification_error"))
        except Exception:
            return "Verification is not available for this ASURITE", 403

    verification_state = session.get("verification_state", {})
    verification_state.update(
        {
            "user_id": user_record_id,
            "asurite": asurite,
            "email": email,
            "cas_complete": True,
            "relay_state": relay_state or verification_state.get("relay_state"),
        }
    )
    session["verification_state"] = verification_state

    session["cas_user"] = {
        "username": asurite,
        "attributes": attributes,
    }

    next_step = _safe_redirect(relay_state) or _safe_redirect(
        verification_state.get("relay_state")
    )
    if next_step:
        return redirect(next_step)

    try:
        home_url = url_for("hello_world")
    except Exception:
        home_url = None

    if home_url:
        return redirect(home_url)

    return {
        "status": "cas_complete",
        "asurite": asurite,
        "email": email,
        "attributes": attributes,
    }


@cas_bp.route("/auth/logout", methods=["POST"])
def cas_logout():
    logger.info("User requested logout from CAS and Discord sessions")
    redirect_url = url_for("hello_world")

    preserved_keys = {"_fresh", "_id", "_permanent"}
    keys_to_remove = [key for key in list(session.keys()) if key not in preserved_keys]
    for key in keys_to_remove:
        session.pop(key, None)

    if CONFIG.CAS_LOGOUT_URL:
        try:
            target = url_for("hello_world", _external=True)
            return redirect(_append_query(CONFIG.CAS_LOGOUT_URL, {"service": target}))
        except Exception:
            logger.warning("Failed to build external logout redirect", exc_info=True)

    return redirect(redirect_url)
