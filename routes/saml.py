from __future__ import annotations

import json
import logging
from typing import Iterable, Mapping

from flask import (
    Blueprint,
    make_response,
    redirect,
    request,
    session,
    url_for,
)
from saml2 import BINDING_HTTP_POST, BINDING_HTTP_REDIRECT
from saml2.client import Saml2Client
from saml2.config import Config
from saml2.response import StatusAuthnFailed, StatusError
from sqlalchemy import select

from utils.database import User, session_scope
from utils.metadata import METADATA_CONFIG, ensure_metadata_on_startup
from utils.settings import CONFIG

saml_bp = Blueprint("saml", __name__)
logger = logging.getLogger(__name__)


def _build_saml_client() -> Saml2Client:
    cfg = Config()
    cfg.load(METADATA_CONFIG.SAML_CONFIG)
    return Saml2Client(config=cfg)


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


@saml_bp.route("/auth/saml/login")
def saml_login():
    relay_state = request.args.get("next")
    client = _build_saml_client()

    session_id, result = client.prepare_for_authenticate(
        relay_state=relay_state,
        binding=BINDING_HTTP_REDIRECT,
    )

    session["saml_request_id"] = session_id

    if result["method"] == "GET":
        headers = dict(result.get("headers", []))
        location = headers.get("Location") or result.get("url")
        if not location:
            return "Unable to determine redirect URL for SAML authentication", 500
        return redirect(location)

    if result["method"] == "POST":
        response = make_response(result["data"])
        for header, value in result.get("headers", []):
            response.headers[header] = value
        return response

    return "Unsupported SAML authentication method", 500


@saml_bp.route("/auth/saml/acs", methods=["POST"])
def saml_acs():
    saml_response = request.form.get("SAMLResponse")
    if not saml_response:
        return "Missing SAMLResponse", 400

    client = _build_saml_client()
    request_id = session.pop("saml_request_id", None)
    relay_state = request.form.get("RelayState") or request.args.get("RelayState")

    outstanding_queries = None
    if request_id:
        outstanding_queries = {request_id: {"relay_state": relay_state}}

    try:
        authn_response = client.parse_authn_request_response(
            saml_response,
            BINDING_HTTP_POST,
            outstanding=outstanding_queries,
        )
    except (StatusError, StatusAuthnFailed) as exc:
        logger.warning("SAML authentication failed: %s", exc)
        return f"SAML authentication failed: {exc}", 401
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error processing SAML response")
        return f"Error processing SAML response: {exc}", 500

    raw_attributes = authn_response.ava or {}
    attribute_lists: dict[str, list[str]] = {}
    for key, value in raw_attributes.items():
        if isinstance(value, (list, tuple, set)):
            attribute_lists[key] = [
                str(item) for item in value if item not in (None, "")
            ]
        elif value not in (None, ""):
            attribute_lists[key] = [str(value)]
        else:
            attribute_lists[key] = []

    attribute_map = CONFIG.SAML_ATTRIBUTE_MAP
    asurite = _first_attribute(attribute_lists, attribute_map["asurite"])
    email = _first_attribute(attribute_lists, attribute_map["email"])
    full_name = _first_attribute(attribute_lists, attribute_map["full_name"])
    first_name = _first_attribute(attribute_lists, attribute_map["first_name"])
    last_name = _first_attribute(attribute_lists, attribute_map["last_name"])

    affiliations_values: list[str] = []
    for key in attribute_map["affiliations"]:
        values = attribute_lists.get(key)
        if values:
            affiliations_values = values
            break

    subject = authn_response.get_subject()
    name_id = subject.text if subject is not None else None

    if not asurite and name_id:
        logger.info("Falling back to SAML NameID for ASURITE attribute")
        asurite = name_id

    if not asurite:
        logger.error(
            "SAML response missing ASURITE identifier; available attribute keys: %s",
            sorted(attribute_lists.keys()),
        )
        return "SAML assertion missing required ASURITE attribute", 400

    if not email:
        logger.error(
            "SAML response missing email attribute for %s; available attribute keys: %s",
            asurite,
            sorted(attribute_lists.keys()),
        )
        return "SAML assertion missing required email attribute", 400

    try:
        session_info = authn_response.session_info() or {}
    except Exception:
        logger.warning(
            "Unable to extract session info from SAML response", exc_info=True
        )
        session_info = {}

    session_index = session_info.get("session_index")
    if isinstance(session_index, (list, tuple, set)):
        session_index = next(
            (item for item in session_index if item not in (None, "")), None
        )
    if session_index and not isinstance(session_index, str):
        session_index = str(session_index)

    if not name_id:
        name_id = session_info.get("name_id")

    if not name_id:
        name_id = session.get("saml_user", {}).get("name_id")

    if not name_id:
        name_id = asurite

    if name_id and not isinstance(name_id, str):
        name_id = str(name_id)

    user_record_id: int | None = None
    with session_scope() as db_session:
        stmt = select(User).where(User.asurite_id == asurite)
        user = db_session.execute(stmt).scalar_one_or_none()

        if user is None:
            user = User(asurite_id=asurite, email=email)
            db_session.add(user)

        user.email = email
        if full_name:
            user.full_name = full_name
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name
        if affiliations_values:
            user.affiliations = ",".join(sorted(set(affiliations_values)))

        user.saml_session_index = session_index
        user.saml_attributes = json.dumps(attribute_lists)

        db_session.flush()
        user_record_id = user.id

    verification_state = session.get("verification_state", {})
    verification_state.update(
        {
            "user_id": user_record_id,
            "asurite": asurite,
            "email": email,
            "saml_complete": True,
            "relay_state": relay_state or verification_state.get("relay_state"),
        }
    )
    session["verification_state"] = verification_state

    session["saml_user"] = {
        "name_id": name_id,
        "session_index": session_index,
        "attributes": attribute_lists,
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

    message = {
        "status": "saml_complete",
        "asurite": asurite,
        "email": email,
    }
    return message


@saml_bp.route("/saml/metadata")
def saml_metadata():
    metadata_path = ensure_metadata_on_startup()
    if not metadata_path.exists():
        return "SP metadata file not found", 404

    response = make_response(metadata_path.read_bytes())
    response.headers["Content-Type"] = "application/xml"
    response.headers["Content-Disposition"] = "inline; filename=sp-metadata.xml"
    response.headers["Cache-Control"] = "no-cache"
    return response


@saml_bp.route("/auth/logout", methods=["POST"])
def saml_logout():
    logger.info("User requested logout from ASU and Discord sessions")
    redirect_url = url_for("hello_world")

    preserved_keys = {"_fresh", "_id", "_permanent"}
    keys_to_remove = [key for key in list(session.keys()) if key not in preserved_keys]
    for key in keys_to_remove:
        session.pop(key, None)

    return redirect(redirect_url)
