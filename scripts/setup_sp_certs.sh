#!/usr/bin/env bash
#
# setup_sp_certs.sh
# Copy the LetsEncrypt SP certificate/key into the app's certs directory,
# install a certbot deploy hook to repeat the process on renewal, and refresh
# the SAML metadata inside the running container.
#
# Usage: sudo ./scripts/setup_sp_certs.sh

set -euo pipefail

###############################################################################
# CONFIGURATION (edit to match your environment)
###############################################################################
DOMAIN="verify.devil2devil.asu.edu"      # FQDN managed by certbot
APP_DIR="/srv/forklift"                  # Root of the Forklift repo on the server
APP_USER="ubuntu"                        # Unix user that should own the copied certs
USE_FULLCHAIN="false"                    # Set to "true" if IdP expects fullchain.pem
APP_SERVICE=""                           # Optional: systemd unit to restart post-deploy

# Container integration (optional, used to trigger metadata refresh)
COMPOSE_CMD="docker compose"             # Change if you use plain docker-compose
COMPOSE_WORKDIR="${APP_DIR}"             # Directory containing docker-compose.yml
COMPOSE_SERVICE="forklift"               # Service name running the Flask app

###############################################################################

CERT_SRC_DIR="/etc/letsencrypt/live/${DOMAIN}"
DEST_DIR="${APP_DIR}/certs"
HOOK_PATH="/etc/letsencrypt/renewal-hooks/deploy/10_deploy_sp_certs.sh"
LOGFILE="/var/log/letsencrypt/deploy_sp_certs.log"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "This script must be run as root. Use: sudo bash $0"
  exit 2
fi

if [[ "${USE_FULLCHAIN}" == "true" || "${USE_FULLCHAIN}" == "1" ]]; then
  CERT_FILE_NAME="fullchain.pem"
else
  CERT_FILE_NAME="cert.pem"
fi

CERT_SRC_PATH="${CERT_SRC_DIR}/${CERT_FILE_NAME}"
KEY_SRC_PATH="${CERT_SRC_DIR}/privkey.pem"

echo "DOMAIN           = ${DOMAIN}"
echo "Source cert      = ${CERT_SRC_PATH}"
echo "Source key       = ${KEY_SRC_PATH}"
echo "Destination dir  = ${DEST_DIR}"
echo "App user         = ${APP_USER}"
echo "Use fullchain    = ${USE_FULLCHAIN}"
[[ -n "${APP_SERVICE}" ]] && echo "Restart service  = ${APP_SERVICE}"
[[ -n "${COMPOSE_SERVICE}" ]] && echo "Compose service  = ${COMPOSE_SERVICE}"

if [[ ! -f "${CERT_SRC_PATH}" ]]; then
  echo "ERROR: cert not found at ${CERT_SRC_PATH}"
  exit 3
fi
if [[ ! -f "${KEY_SRC_PATH}" ]]; then
  echo "ERROR: key not found at ${KEY_SRC_PATH}"
  exit 4
fi

mkdir -p "${DEST_DIR}"
chown root:root "${DEST_DIR}"
chmod 755 "${DEST_DIR}"

copy_atomic() {
  local src="$1" dst="$2" mode="$3" owner="$4" group="$5"
  local tmp="${dst}.new.$$"
  cp "${src}" "${tmp}"
  chmod "${mode}" "${tmp}"
  chown "${owner}:${group}" "${tmp}"
  mv -f "${tmp}" "${dst}"
}

echo "Copying cert and key into ${DEST_DIR} ..."
copy_atomic "${CERT_SRC_PATH}" "${DEST_DIR}/sp.crt" 644 root "${APP_USER}"
copy_atomic "${KEY_SRC_PATH}"  "${DEST_DIR}/sp.key" 600 root "${APP_USER}"

chown "${APP_USER}:${APP_USER}" "${DEST_DIR}/sp.crt" "${DEST_DIR}/sp.key"
chmod 644 "${DEST_DIR}/sp.crt"
chmod 600 "${DEST_DIR}/sp.key"

echo "Setting up certbot deploy hook at ${HOOK_PATH} ..."

cat > "${HOOK_PATH}" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail

DOMAIN="__DOMAIN__"
APP_DIR="__APP_DIR__"
DEST_DIR="${APP_DIR}/certs"
APP_USER="__APP_USER__"
USE_FULLCHAIN="__USE_FULLCHAIN__"
CERT_SRC_DIR="/etc/letsencrypt/live/${DOMAIN}"
LOGFILE="__LOGFILE__"
APP_SERVICE="__APP_SERVICE__"
COMPOSE_CMD="__COMPOSE_CMD__"
COMPOSE_WORKDIR="__COMPOSE_WORKDIR__"
COMPOSE_SERVICE="__COMPOSE_SERVICE__"

if [[ "${USE_FULLCHAIN}" == "true" || "${USE_FULLCHAIN}" == "1" ]]; then
  CERT_FILE_NAME="fullchain.pem"
else
  CERT_FILE_NAME="cert.pem"
fi

CERT_SRC_PATH="${CERT_SRC_DIR}/${CERT_FILE_NAME}"
KEY_SRC_PATH="${CERT_SRC_DIR}/privkey.pem"

mkdir -p "${DEST_DIR}"
chown root:root "${DEST_DIR}"
chmod 755 "${DEST_DIR}"

tmp_cert="${DEST_DIR}/sp.crt.new.$$"
tmp_key="${DEST_DIR}/sp.key.new.$$"

cp "${CERT_SRC_PATH}" "${tmp_cert}"
cp "${KEY_SRC_PATH}" "${tmp_key}"

chmod 644 "${tmp_cert}"
chmod 600 "${tmp_key}"
chown root:"${APP_USER}" "${tmp_cert}" "${tmp_key}"

mv -f "${tmp_cert}" "${DEST_DIR}/sp.crt"
mv -f "${tmp_key}" "${DEST_DIR}/sp.key"

chown "${APP_USER}:${APP_USER}" "${DEST_DIR}/sp.crt" "${DEST_DIR}/sp.key"
chmod 644 "${DEST_DIR}/sp.crt"
chmod 600 "${DEST_DIR}/sp.key"

echo "$(date -u) deployed certs for ${DOMAIN} to ${DEST_DIR}" >> "${LOGFILE}" || true

if [[ -n "${COMPOSE_SERVICE}" ]]; then
  if [[ -n "${COMPOSE_WORKDIR}" ]]; then
    pushd "${COMPOSE_WORKDIR}" >/dev/null || exit 0
  fi
  ${COMPOSE_CMD} exec -T "${COMPOSE_SERVICE}" python -m utils.metadata --refresh-if-expired || true
  if [[ -n "${COMPOSE_WORKDIR}" ]]; then
    popd >/dev/null || true
  fi
fi

if [[ -n "${APP_SERVICE}" ]]; then
  systemctl try-restart "${APP_SERVICE}" || true
fi

HOOK

sed -i \
  -e "s|__DOMAIN__|${DOMAIN}|g" \
  -e "s|__APP_DIR__|${APP_DIR}|g" \
  -e "s|__APP_USER__|${APP_USER}|g" \
  -e "s|__USE_FULLCHAIN__|${USE_FULLCHAIN}|g" \
  -e "s|__LOGFILE__|${LOGFILE}|g" \
  -e "s|__APP_SERVICE__|${APP_SERVICE}|g" \
  -e "s|__COMPOSE_CMD__|${COMPOSE_CMD}|g" \
  -e "s|__COMPOSE_WORKDIR__|${COMPOSE_WORKDIR}|g" \
  -e "s|__COMPOSE_SERVICE__|${COMPOSE_SERVICE}|g" \
  "${HOOK_PATH}"

chmod 755 "${HOOK_PATH}"

echo "Deploy hook created and made executable."

echo "Running the hook now to copy current certs and refresh metadata..."
bash "${HOOK_PATH}"

echo "Listing cert files in ${DEST_DIR}:"
ls -l "${DEST_DIR}"

echo "Done. Certs copied to ${DEST_DIR}/sp.crt and ${DEST_DIR}/sp.key"
echo "The deploy hook will run automatically after certbot renewals and refresh SAML metadata."
echo "Check logs at ${LOGFILE} for deploy-run entries."

cat <<EOF

REMINDERS:
 - Adjust APP_DIR/APP_USER if your deployment lives elsewhere.
 - If you change docker-compose commands (e.g., legacy docker-compose binary),
   update COMPOSE_CMD accordingly.
 - To test the deploy hook end-to-end, run:
     sudo certbot renew --dry-run -v

EOF
