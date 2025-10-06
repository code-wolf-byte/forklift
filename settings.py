"""SAML configuration helpers for generating Forklift SP metadata.

Populate the environment variables or adjust the defaults below to match
your deployment before generating metadata. These settings are consumed by
pysaml2 when building the service provider (SP) metadata.
"""

from pathlib import Path
import os


def _str_to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

from saml2 import BINDING_HTTP_POST, BINDING_HTTP_REDIRECT

BASE_DIR = Path(__file__).resolve().parent

# Base HTTPS URL where your application is hosted. Update this to match the
# environment that will service SAML requests.
SAML_BASE_URL = os.getenv("SAML_BASE_URL", "https://verify.devil2devil.asu.edu")

# Unique identifier for your SP. This should generally be the HTTPS URL where
# you expose your SP metadata so partners can refresh it automatically.
ENTITY_ID = os.getenv("SAML_ENTITY_ID", f"{SAML_BASE_URL}/saml/metadata")

# Assertion Consumer Service (ACS) endpoint where the IdP posts assertions.
ACS_URL = os.getenv("SAML_ACS_URL", f"{SAML_BASE_URL}/auth/saml/acs")

# Optional Single Logout Service endpoint. Leave empty if you do not support SLO.
SLS_URL = os.getenv("SAML_SLS_URL", f"{SAML_BASE_URL}/auth/saml/slo")

# Local certificate and private key used for signing metadata and SAML messages.
CERT_FILE = Path(os.getenv("SAML_CERT_FILE", "certs/sp.crt"))
KEY_FILE = Path(os.getenv("SAML_KEY_FILE", "certs/sp.key"))

# Optional: path (or comma-separated list) to IdP metadata files consumed by the SP.
default_idp_metadata = BASE_DIR / "idp-metadata.xml"
_idp_metadata_raw = os.getenv("SAML_IDP_METADATA", str(default_idp_metadata))
IDP_METADATA_FILES = [p.strip() for p in _idp_metadata_raw.split(",") if p.strip()]

# How long (in days) generated metadata should be considered valid by partners.
METADATA_VALIDITY_DAYS = int(os.getenv("SAML_METADATA_VALIDITY_DAYS", "365"))

# Override if xmlsec is installed in a non-standard location.
_default_xmlsec = BASE_DIR / "scripts" / "xmlsec-wrapper.sh"
XMLSEC_BINARY = os.getenv(
    "XMLSEC_BINARY",
    str(_default_xmlsec) if _default_xmlsec.exists() else "/usr/bin/xmlsec1",
)

# Toggle certificate validation (set to true once you switch to a CA-signed cert).
VALIDATE_CERTIFICATE = _str_to_bool(os.getenv("SAML_VALIDATE_CERTIFICATE"), default=False)

# Enable the OpenSSL legacy provider automatically when the helper config file exists.
_legacy_openssl_conf = BASE_DIR / "openssl-legacy.cnf"
if _legacy_openssl_conf.exists() and "OPENSSL_CONF" not in os.environ:
    os.environ["OPENSSL_CONF"] = str(_legacy_openssl_conf)


def build_saml_config():
    """Return a pysaml2 configuration dictionary for the SP."""
    saml_config = {
        "entityid": ENTITY_ID,
        "service": {
            "sp": {
                "name": "Forklift Verification",
                "endpoints": {
                    "assertion_consumer_service": [
                        (ACS_URL, BINDING_HTTP_POST),
                    ],
                    # Only include the SLS endpoint if you actually implement it.
                    "single_logout_service": [
                        (SLS_URL, BINDING_HTTP_REDIRECT),
                    ] if SLS_URL else [],
                },
                # Adjust depending on whether you sign AuthnRequests.
                "authn_requests_signed": True,
                "logout_requests_signed": True,
                "want_assertions_signed": True,
                "allow_unsolicited": False,
            },
        },
        "key_file": str(KEY_FILE),
        "cert_file": str(CERT_FILE),
        "ca_certs": str(CERT_FILE),
        "debug": False,
        "xmlsec_binary": XMLSEC_BINARY,
        "validate_certificate": VALIDATE_CERTIFICATE,
        # Attribute mapping directory optional; add if you need custom mappings.
        "attribute_map_dir": os.getenv("SAML_ATTRIBUTE_MAP_DIR", ""),
        "valid_for": METADATA_VALIDITY_DAYS,
    }

    if IDP_METADATA_FILES:
        existing_metadata = [str(Path(p)) for p in IDP_METADATA_FILES if Path(p).exists()]
        if existing_metadata:
            saml_config["metadata"] = {"local": existing_metadata}

    # Drop empty single logout service list if not configured.
    endpoints = saml_config["service"]["sp"]["endpoints"]
    if not endpoints["single_logout_service"]:
        endpoints.pop("single_logout_service")

    if not saml_config.get("attribute_map_dir"):
        saml_config.pop("attribute_map_dir", None)

    return saml_config


# Convenience constant for callers that prefer a module-level dict.
SAML_CONFIG = build_saml_config()
