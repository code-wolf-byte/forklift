from __future__ import annotations

from typing import Any, Mapping

from saml2 import BINDING_HTTP_POST, BINDING_HTTP_REDIRECT
from saml2.client import Saml2Client
from saml2.config import Config

from utils.metadata import METADATA_CONFIG


class SamlClient:
    """Lightweight wrapper around pysaml2's Saml2Client."""

    def __init__(self, saml_config: Mapping[str, Any]) -> None:
        self._saml_config = saml_config

    def _build_client(self) -> Saml2Client:
        cfg = Config()
        cfg.load(self._saml_config)
        return Saml2Client(config=cfg)

    def prepare_for_authenticate(
        self, *, relay_state: str | None, binding: str = BINDING_HTTP_REDIRECT
    ):
        client = self._build_client()
        return client.prepare_for_authenticate(
            relay_state=relay_state,
            binding=binding,
        )

    def parse_authn_request_response(
        self,
        saml_response: str,
        binding: str = BINDING_HTTP_POST,
        *,
        outstanding: Mapping[str, Any] | None = None,
    ):
        client = self._build_client()
        return client.parse_authn_request_response(
            saml_response,
            binding,
            outstanding=outstanding,
        )


saml_client = SamlClient(METADATA_CONFIG.SAML_CONFIG)
