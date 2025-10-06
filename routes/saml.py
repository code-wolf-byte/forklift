from __future__ import annotations

from pathlib import Path

from flask import Blueprint, make_response, redirect, request, session

from saml2 import BINDING_HTTP_POST, BINDING_HTTP_REDIRECT
from saml2.client import Saml2Client
from saml2.config import Config
from saml2.response import StatusAuthnFailed, StatusError

import settings

saml_bp = Blueprint("saml", __name__)


def _build_saml_client() -> Saml2Client:
    cfg = Config()
    cfg.load(settings.SAML_CONFIG)
    return Saml2Client(config=cfg)


@saml_bp.route("/auth/saml/login")
def saml_login():
    relay_state = request.args.get("next")
    client = _build_saml_client()

    # Use redirect binding by default; pysaml2 will fall back to POST if required.
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

    try:
        authn_response = client.parse_authn_request_response(
            saml_response,
            BINDING_HTTP_POST,
            request_id=request_id,
        )
    except (StatusError, StatusAuthnFailed) as exc:
        return f"SAML authentication failed: {exc}", 401
    except Exception as exc:
        return f"Error processing SAML response: {exc}", 500

    identity = authn_response.ava or {}
    attributes = {
        key: values[0] if isinstance(values, (list, tuple)) and len(values) == 1 else values
        for key, values in identity.items()
    }

    subject = authn_response.get_subject()
    user_info = {
        "name_id": subject.text if subject is not None else None,
        "session_index": authn_response.session_index(),
        "attributes": attributes,
        "relay_state": request.form.get("RelayState"),
    }

    session["saml_user"] = user_info
    return user_info


@saml_bp.route("/saml/metadata")
def saml_metadata():
    metadata_path = Path(settings.BASE_DIR, "sp-metadata.xml")
    if not metadata_path.exists():
        return "SP metadata file not found", 404

    response = make_response(metadata_path.read_bytes())
    response.headers["Content-Type"] = "application/xml"
    response.headers["Content-Disposition"] = "inline; filename=sp-metadata.xml"
    response.headers["Cache-Control"] = "no-cache"
    return response
