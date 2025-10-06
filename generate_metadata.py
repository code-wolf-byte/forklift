"""Generate signed SAML SP metadata using pysaml2 and the local settings."""

from __future__ import annotations

import argparse
from pathlib import Path

from saml2 import config as saml2_config
from saml2.metadata import create_metadata_string
from saml2.sigver import SignatureError

import settings


def write_metadata(output_path: Path, xml_payload: bytes | str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(xml_payload, str):
        output_path.write_text(xml_payload, encoding="utf-8")
    else:
        output_path.write_bytes(xml_payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SP metadata")
    parser.add_argument(
        "--output",
        default="sp-metadata.xml",
        help="Path to the metadata XML file to create (default: sp-metadata.xml)",
    )
    parser.add_argument(
        "--unsigned",
        action="store_true",
        help="Skip signing the metadata even if key/cert are configured",
    )
    parser.add_argument(
        "--valid-days",
        type=int,
        default=settings.METADATA_VALIDITY_DAYS,
        help="Number of days the metadata should be valid for",
    )

    args = parser.parse_args()

    cfg = saml2_config.Config()
    cfg.load(settings.SAML_CONFIG)

    output_path = Path(args.output)
    should_sign = not args.unsigned

    # pysaml2 expects the validity window expressed in hours.
    valid_hours = args.valid_days * 24 if args.valid_days else None

    cert_path = str(settings.CERT_FILE) if should_sign else None
    key_path = str(settings.KEY_FILE) if should_sign else None

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
            "xmlsec failed to sign the metadata. Check that certs/sp.crt and certs/sp.key exist "
            "and ensure the certificate is trusted (set SAML_VALIDATE_CERTIFICATE=true when "
            "using a CA-signed cert, or false for self-signed)."
        )
        raise RuntimeError(hint) from exc

    write_metadata(output_path, metadata_xml)
    print(f"Wrote {'signed' if should_sign else 'unsigned'} metadata to {output_path}")


if __name__ == "__main__":
    main()
