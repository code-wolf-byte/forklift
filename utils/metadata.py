"""Helpers for generating and maintaining Forklift SAML metadata."""

from __future__ import annotations

import argparse
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from saml2 import BINDING_HTTP_POST, BINDING_HTTP_REDIRECT, config as saml2_config
from saml2.metadata import create_metadata_string
from saml2.sigver import SignatureError


logger = logging.getLogger(__name__)


class MetadataConfig:
    """Encapsulate environment-driven settings for SAML metadata generation."""

    def __init__(self) -> None:
        project_root = Path(__file__).resolve().parent.parent
        self.BASE_DIR = project_root

        self.METADATA_PATH = Path(
            os.getenv("SAML_METADATA_PATH", project_root / "sp-metadata.xml")
        )

        self.SAML_BASE_URL = os.getenv("SAML_BASE_URL", "https://verify.devil2devil.asu.edu")
        self.ENTITY_ID = os.getenv("SAML_ENTITY_ID", f"{self.SAML_BASE_URL}/saml/metadata")
        self.ACS_URL = os.getenv("SAML_ACS_URL", f"{self.SAML_BASE_URL}/auth/saml/acs")
        self.SLS_URL = os.getenv("SAML_SLS_URL", f"{self.SAML_BASE_URL}/auth/saml/slo")

        self.CERT_FILE = Path(os.getenv("SAML_CERT_FILE", project_root / "certs/sp.crt"))
        self.KEY_FILE = Path(os.getenv("SAML_KEY_FILE", project_root / "certs/sp.key"))

        default_idp_metadata = project_root / "idp-metadata.xml"
        idp_metadata_raw = os.getenv("SAML_IDP_METADATA", str(default_idp_metadata))
        self.IDP_METADATA_FILES = [p.strip() for p in idp_metadata_raw.split(",") if p.strip()]

        self.METADATA_VALIDITY_DAYS = int(os.getenv("SAML_METADATA_VALIDITY_DAYS", "365"))

        default_xmlsec = project_root / "scripts" / "xmlsec-wrapper.sh"
        self.XMLSEC_BINARY = os.getenv(
            "XMLSEC_BINARY",
            str(default_xmlsec) if default_xmlsec.exists() else "/usr/bin/xmlsec1",
        )

        self.VALIDATE_CERTIFICATE = self._str_to_bool(
            os.getenv("SAML_VALIDATE_CERTIFICATE"),
            default=False,
        )

        self.METADATA_REFRESH_INTERVAL_SECONDS = max(
            60,
            int(os.getenv("SAML_METADATA_REFRESH_INTERVAL_SECONDS", "600")),
        )
        self.METADATA_REFRESH_LEEWAY_SECONDS = max(
            0,
            int(os.getenv("SAML_METADATA_REFRESH_LEEWAY_SECONDS", "300")),
        )

        self._ensure_legacy_openssl(project_root)
        self.SAML_CONFIG = self.build_saml_config()

    @staticmethod
    def _str_to_bool(value: str | None, default: bool = False) -> bool:
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def _ensure_legacy_openssl(self, project_root: Path) -> None:
        legacy_conf = project_root / "openssl-legacy.cnf"
        if legacy_conf.exists() and "OPENSSL_CONF" not in os.environ:
            os.environ["OPENSSL_CONF"] = str(legacy_conf)

    def build_saml_config(self) -> dict[str, Any]:
        saml_config: dict[str, Any] = {
            "entityid": self.ENTITY_ID,
            "service": {
                "sp": {
                    "name": "Forklift Verification",
                    "endpoints": {
                        "assertion_consumer_service": [
                            (self.ACS_URL, BINDING_HTTP_POST),
                        ],
                        "single_logout_service": (
                            [(self.SLS_URL, BINDING_HTTP_REDIRECT)] if self.SLS_URL else []
                        ),
                    },
                    "authn_requests_signed": True,
                    "logout_requests_signed": True,
                    "want_assertions_signed": True,
                    "allow_unsolicited": False,
                },
            },
            "key_file": str(self.KEY_FILE),
            "cert_file": str(self.CERT_FILE),
            "ca_certs": str(self.CERT_FILE),
            "debug": False,
            "xmlsec_binary": self.XMLSEC_BINARY,
            "validate_certificate": self.VALIDATE_CERTIFICATE,
            "attribute_map_dir": os.getenv("SAML_ATTRIBUTE_MAP_DIR", ""),
            "valid_for": self.METADATA_VALIDITY_DAYS,
        }

        if self.IDP_METADATA_FILES:
            existing_metadata = [
                str(Path(path))
                for path in self.IDP_METADATA_FILES
                if Path(path).exists()
            ]
            if existing_metadata:
                saml_config["metadata"] = {"local": existing_metadata}

        endpoints = saml_config["service"]["sp"]["endpoints"]
        if not endpoints["single_logout_service"]:
            endpoints.pop("single_logout_service")

        if not saml_config.get("attribute_map_dir"):
            saml_config.pop("attribute_map_dir", None)

        return saml_config


class MetadataGenerator:
    """Encapsulates SAML metadata generation and signing logic."""

    def __init__(self, metadata_config: MetadataConfig) -> None:
        self._config = metadata_config
        self._default_valid_days = metadata_config.METADATA_VALIDITY_DAYS

    def _read_valid_until(self, metadata_path: Path) -> datetime:
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {metadata_path}")

        try:
            root = ElementTree.fromstring(metadata_path.read_text(encoding="utf-8"))
        except ElementTree.ParseError as exc:
            raise ValueError(f"Cannot parse metadata XML: {metadata_path}") from exc

        valid_until_raw = next(
            (elem.attrib.get("validUntil") for elem in root.iter() if "validUntil" in elem.attrib),
            None,
        )
        if valid_until_raw is None:
            raise ValueError("Metadata is missing validUntil; cannot determine expiration.")

        if valid_until_raw.endswith("Z"):
            valid_until_raw = f"{valid_until_raw[:-1]}+00:00"

        try:
            valid_until = datetime.fromisoformat(valid_until_raw)
        except ValueError as exc:
            raise ValueError(f"Unexpected validUntil format: {valid_until_raw}") from exc

        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)

        return valid_until

    @staticmethod
    def _write_metadata(output_path: Path, xml_payload: bytes | str) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(xml_payload, str):
            output_path.write_text(xml_payload, encoding="utf-8")
        else:
            output_path.write_bytes(xml_payload)

    def generate_metadata(
        self,
        output_path: str | Path | None = None,
        *,
        valid_days: int | None = None,
        unsigned: bool = False,
    ) -> Path:
        cfg = saml2_config.Config()
        cfg.load(self._config.SAML_CONFIG)

        output_path = Path(output_path or self._config.METADATA_PATH)
        should_sign = not unsigned
        selected_valid_days = valid_days if valid_days is not None else self._default_valid_days

        # pysaml2 expects the validity window expressed in hours.
        valid_hours = selected_valid_days * 24 if selected_valid_days else None

        cert_path = (
            str(self._config.CERT_FILE)
            if should_sign and self._config.CERT_FILE is not None
            else None
        )
        key_path = (
            str(self._config.KEY_FILE)
            if should_sign and self._config.KEY_FILE is not None
            else None
        )

        try:
            metadata_xml = create_metadata_string(
                None,
                config=cfg,
                valid=valid_hours,
                sign=should_sign,
                cert=cert_path,
                keyfile=key_path,
            )
        except SignatureError as exc:
            hint = (
                "xmlsec failed to sign the metadata. Check that the configured certificate/key exist "
                "and ensure the certificate is trusted "
                "(set SAML_VALIDATE_CERTIFICATE=true when using a CA-signed cert, or false for self-signed)."
            )
            raise RuntimeError(hint) from exc

        self._write_metadata(output_path, metadata_xml)
        return output_path

    def metadata_has_expired(
        self,
        metadata_path: str | Path | None = None,
        *,
        at_time: datetime | None = None,
    ) -> bool:
        """Return True when the metadata file has expired according to validUntil."""
        metadata_path = Path(metadata_path or self._config.METADATA_PATH)
        valid_until = self._read_valid_until(metadata_path)

        comparison_time = at_time or datetime.now(timezone.utc)
        if comparison_time.tzinfo is None:
            comparison_time = comparison_time.replace(tzinfo=timezone.utc)

        return comparison_time >= valid_until

    def metadata_valid_until(
        self,
        metadata_path: str | Path | None = None,
    ) -> datetime:
        """Return the metadata validUntil timestamp."""
        metadata_path = Path(metadata_path or self._config.METADATA_PATH)
        return self._read_valid_until(metadata_path)

    def ensure_metadata(
        self,
        metadata_path: str | Path | None = None,
        *,
        valid_days: int | None = None,
        unsigned: bool = False,
        check_time: datetime | None = None,
    ) -> bool:
        """Regenerate metadata if the file is missing or expired; return True when refreshed."""
        metadata_path = Path(metadata_path or self._config.METADATA_PATH)
        comparison_time = check_time or datetime.now(timezone.utc)
        if comparison_time.tzinfo is None:
            comparison_time = comparison_time.replace(tzinfo=timezone.utc)
        try:
            expired = self.metadata_has_expired(
                metadata_path,
                at_time=comparison_time,
            )
        except FileNotFoundError:
            expired = True

        if expired:
            self.generate_metadata(
                output_path=metadata_path,
                valid_days=valid_days,
                unsigned=unsigned,
            )
            return True

        return False


METADATA_CONFIG = MetadataConfig()
METADATA_GENERATOR = MetadataGenerator(METADATA_CONFIG)

_REFRESH_THREAD: threading.Thread | None = None
_REFRESH_STOP = threading.Event()
_SCHEDULER_UNSIGNED = False


def _next_refresh_delay() -> float:
    """Determine how long to wait before the next metadata check."""
    interval = METADATA_CONFIG.METADATA_REFRESH_INTERVAL_SECONDS
    leeway = METADATA_CONFIG.METADATA_REFRESH_LEEWAY_SECONDS
    try:
        valid_until = METADATA_GENERATOR.metadata_valid_until(
            metadata_path=METADATA_CONFIG.METADATA_PATH
        )
    except FileNotFoundError:
        return 0.0
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Unable to read metadata validity; using default interval", exc_info=exc)
        return float(interval)

    now = datetime.now(timezone.utc)
    refresh_at = valid_until - timedelta(seconds=leeway)
    delay = (refresh_at - now).total_seconds()
    if delay <= 0:
        return 0.0
    return min(delay, float(interval))


def _metadata_refresh_loop() -> None:
    """Ensure metadata refreshes in the background without downtime."""
    while not _REFRESH_STOP.is_set():
        try:
            check_time = datetime.now(timezone.utc) + timedelta(
                seconds=METADATA_CONFIG.METADATA_REFRESH_LEEWAY_SECONDS
            )
            refreshed = METADATA_GENERATOR.ensure_metadata(
                metadata_path=METADATA_CONFIG.METADATA_PATH,
                valid_days=METADATA_CONFIG.METADATA_VALIDITY_DAYS,
                unsigned=_SCHEDULER_UNSIGNED,
                check_time=check_time,
            )
            if refreshed:
                logger.info("Regenerated SAML metadata at %s", METADATA_CONFIG.METADATA_PATH)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to refresh SAML metadata")

        delay = max(1.0, _next_refresh_delay())
        if _REFRESH_STOP.wait(delay):
            break


def start_metadata_scheduler() -> None:
    """Start the background scheduler that keeps metadata fresh."""
    global _REFRESH_THREAD
    if _REFRESH_THREAD and _REFRESH_THREAD.is_alive():
        return

    _REFRESH_STOP.clear()
    _REFRESH_THREAD = threading.Thread(
        target=_metadata_refresh_loop,
        name="metadata-refresh",
        daemon=True,
    )
    _REFRESH_THREAD.start()


def stop_metadata_scheduler() -> None:
    """Stop the background metadata scheduler."""
    global _REFRESH_THREAD
    if not _REFRESH_THREAD:
        return
    _REFRESH_STOP.set()
    _REFRESH_THREAD.join(timeout=5)
    _REFRESH_THREAD = None


def ensure_metadata_on_startup(*, unsigned: bool = False) -> Path:
    """Ensure metadata exists and is current, returning the active metadata path."""
    global _SCHEDULER_UNSIGNED
    _SCHEDULER_UNSIGNED = unsigned
    METADATA_GENERATOR.ensure_metadata(
        metadata_path=METADATA_CONFIG.METADATA_PATH,
        valid_days=METADATA_CONFIG.METADATA_VALIDITY_DAYS,
        unsigned=unsigned,
    )
    return METADATA_CONFIG.METADATA_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SP metadata")
    parser.add_argument(
        "--output",
        default=str(METADATA_CONFIG.METADATA_PATH),
        help=f"Path to the metadata XML file to create (default: {METADATA_CONFIG.METADATA_PATH})",
    )
    parser.add_argument(
        "--unsigned",
        action="store_true",
        help="Skip signing the metadata even if key/cert are configured",
    )
    parser.add_argument(
        "--valid-days",
        type=int,
        default=METADATA_CONFIG.METADATA_VALIDITY_DAYS,
        help="Number of days the metadata should be valid for",
    )
    parser.add_argument(
        "--refresh-if-expired",
        action="store_true",
        help="Regenerate the metadata only when the existing file has expired",
    )

    args = parser.parse_args()
    generator = METADATA_GENERATOR

    if args.refresh_if_expired:
        regenerated = generator.ensure_metadata(
            metadata_path=args.output,
            valid_days=args.valid_days,
            unsigned=args.unsigned,
        )
        if regenerated:
            signature_state = "unsigned" if args.unsigned else "signed"
            print(f"Metadata expired; refreshed {signature_state} metadata at {args.output}")
        else:
            print(f"Metadata still valid; no action taken for {args.output}")
        return

    output_path = generator.generate_metadata(
        output_path=args.output,
        valid_days=args.valid_days,
        unsigned=args.unsigned,
    )
    signature_state = "unsigned" if args.unsigned else "signed"
    print(f"Wrote {signature_state} metadata to {output_path}")


if __name__ == "__main__":
    main()
