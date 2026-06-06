#!/usr/bin/env bash
# Production resolver for rm-via-allure.nvidia.com (HTTPS port 9999).
# Run from repo: ngts/scripts/ai_rca/server_side/run_server_prod.sh
# Production deploy dir: /root/regression_ai_allure_attachment/src
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${DIR}"

export ALLURE_JSON_RESOLVER_SERVER_BASE="${ALLURE_JSON_RESOLVER_SERVER_BASE:-https://rm-via-allure.nvidia.com:9999}"
export PORT="${PORT:-9999}"
export BIND="${BIND:-0.0.0.0}"

# Plugin JS: sibling AllurClick2RM/plugin_files (set by deploy script)
export ALLURCLICK2RM_PLUGIN_DIR="${ALLURCLICK2RM_PLUGIN_DIR:-${DIR}/AllurClick2RM/plugin_files}"

# Optional: agent JSON fetch from fit69 when /auto path not mounted locally
export RESOLVE_MANUAL_FETCH_BASE="${RESOLVE_MANUAL_FETCH_BASE:-http://fit69.mtl.labs.mlnx}"

# TLS — DigiCert for rm-via-allure.nvidia.com (/root/certification/)
export SSL_CERT_FILE="${SSL_CERT_FILE:-/root/certification/new_rm_digicert.crt}"
export SSL_KEY_FILE="${SSL_KEY_FILE:-/root/certification/rm_allure_new.key}"

_pick_python() {
  local cand ver
  for cand in \
    "${PYTHON_BIN:-}" \
    /root/open_rm_auto/venv/bin/python3 \
    /root/open_rm_auto/venv/bin/python \
    python3.11 python3.10 python3.9 python3.8 python3.7 python3; do
    [[ -z "${cand}" ]] && continue
    if command -v "${cand}" >/dev/null 2>&1 || [[ -x "${cand}" ]]; then
      if ver="$("${cand}" -c 'import sys; print("{}.{}".format(sys.version_info[0], sys.version_info[1]))' 2>/dev/null)"; then
        case "${ver}" in
          3.6|3.7|3.8|3.9|3.10|3.11|3.12|3.13)
            echo "${cand}"
            return 0
            ;;
        esac
      fi
    fi
  done
  return 1
}

PYTHON="$(_pick_python || true)"
if [[ -z "${PYTHON}" ]]; then
  echo "Need Python 3.6+ on this host (set PYTHON_BIN=/path/to/python3)." >&2
  exit 1
fi

echo "Starting ai_rca resolver"
echo "  base=${ALLURE_JSON_RESOLVER_SERVER_BASE}"
echo "  bind=${BIND}:${PORT}"
echo "  plugins=${ALLURCLICK2RM_PLUGIN_DIR}"
echo "  tls cert=${SSL_CERT_FILE}"
echo "  tls key=${SSL_KEY_FILE}"
echo "  python=$(${PYTHON} -V 2>&1)"

exec "${PYTHON}" -u "${DIR}/allure_resolver_server.py"
