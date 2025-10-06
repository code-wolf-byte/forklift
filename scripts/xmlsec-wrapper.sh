#!/bin/bash
CERT_PATH="$(dirname "$0")/../certs/sp.crt"
if [[ "$1" == "--sign" ]]; then
  exec /usr/bin/xmlsec1 "--sign" "--trusted-pem" "$CERT_PATH" "${@:2}"
else
  exec /usr/bin/xmlsec1 "$@"
fi
