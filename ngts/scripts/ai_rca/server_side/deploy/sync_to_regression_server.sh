#!/usr/bin/env bash
# Sync ai_rca resolver + AllurClick2RM plugin files to the production host.
#
# Usage (from sonic-mgmt repo root):
#   ./ngts/scripts/ai_rca/server_side/deploy/sync_to_regression_server.sh
#   ./ngts/scripts/ai_rca/server_side/deploy/sync_to_regression_server.sh root@other-host:/path
#
# Default target: /root/regression_ai_allure_attachment/src on rm-via-allure.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../../../.." && pwd)"
SERVER_SRC="${REPO_ROOT}/ngts/scripts/ai_rca/server_side"
TESTS_AI_RCA="${REPO_ROOT}/tests/common/plugins/allure_wrapper/ai_rca"
PLUGIN_SRC="${REPO_ROOT}/ngts/scripts/AllurClick2RM/plugin_files"
TARGET="${1:-root@rm-via-allure.nvidia.com:/root/regression_ai_allure_attachment/src}"

if [[ ! -d "${SERVER_SRC}" ]]; then
  echo "ai_rca server_side dir not found: ${SERVER_SRC}" >&2
  exit 1
fi
if [[ ! -d "${PLUGIN_SRC}" ]]; then
  echo "AllurClick2RM plugin_files not found: ${PLUGIN_SRC}" >&2
  exit 1
fi

REMOTE="${TARGET%%:*}"
REMOTE_DIR="${TARGET#*:}"
if [[ -z "${REMOTE}" || -z "${REMOTE_DIR}" || "${REMOTE}" == "${TARGET}" ]]; then
  echo "Invalid target (expected user@host:/path): ${TARGET}" >&2
  exit 1
fi

echo "Repo:   ${REPO_ROOT}"
echo "Source: ${SERVER_SRC}"
echo "Target: ${TARGET}"
echo

STAGING="$(mktemp -d)"
trap 'rm -rf "${STAGING}"' EXIT

mkdir -p \
  "${STAGING}/templates" \
  "${STAGING}/embedded_rm_modal" \
  "${STAGING}/AllurClick2RM/plugin_files" \
  "${STAGING}/demo/fixtures"

cp "${SERVER_SRC}/allure_resolver_server.py" \
   "${SERVER_SRC}/misql_pbi_connect.py" \
   "${TESTS_AI_RCA}/resolver_contract.py" \
   "${SERVER_SRC}/attachment_templates.py" \
   "${SERVER_SRC}/embedded_rm_modal_loader.py" \
   "${SERVER_SRC}/run_server_prod.sh" \
   "${STAGING}/"

cp -r "${SERVER_SRC}/templates/." "${STAGING}/templates/"
cp -r "${SERVER_SRC}/embedded_rm_modal/." "${STAGING}/embedded_rm_modal/"
cp -r "${PLUGIN_SRC}/." "${STAGING}/AllurClick2RM/plugin_files/"
cp -r "${SERVER_SRC}/demo/fixtures/." "${STAGING}/demo/fixtures/"

chmod +x "${STAGING}/run_server_prod.sh"

ssh "${REMOTE}" "mkdir -p '${REMOTE_DIR}/AllurClick2RM/plugin_files' '${REMOTE_DIR}/demo/fixtures'"

rsync -avz --delete "${STAGING}/" "${TARGET}/"

echo
echo "Done. On the server:"
echo "  cd ${REMOTE_DIR}"
echo "  ./run_server_prod.sh"
echo
echo "Ensure DigiCert files exist under /root/certification/ (see deploy/ssl.env.example)."
