#!/usr/bin/env bash
set -euo pipefail

: "${REGRESSION_MAIL_VDI_TARGET:?set user@host for the execution VDI}"
: "${REGRESSION_MAIL_REMOTE_ROOT:?set the deployed sonic-mgmt path on the VDI}"
: "${REGRESSION_MAIL_VDI_KNOWN_HOSTS:?set a Jenkins-managed known_hosts file}"

remote_env="${REGRESSION_MAIL_REMOTE_ENV_FILE:-${REGRESSION_MAIL_REMOTE_ROOT}/.regression-mail.env}"
ssh_options=(
    -o BatchMode=yes
    -o ConnectTimeout=30
    -o StrictHostKeyChecking=yes
    -o "UserKnownHostsFile=${REGRESSION_MAIL_VDI_KNOWN_HOSTS}"
)

if [[ -n "${REGRESSION_MAIL_VDI_KEY_FILE:-}" ]]; then
    ssh_options+=(-o IdentitiesOnly=yes -i "${REGRESSION_MAIL_VDI_KEY_FILE}")
fi
if [[ -n "${REGRESSION_MAIL_VDI_PROXY_JUMP:-}" ]]; then
    ssh_options+=(-J "${REGRESSION_MAIL_VDI_PROXY_JUMP}")
fi

quote() {
    printf '%q' "$1"
}

remote_root_q="$(quote "${REGRESSION_MAIL_REMOTE_ROOT}")"
remote_env_q="$(quote "${remote_env}")"
remote_command="set -euo pipefail; cd ${remote_root_q}; "
remote_command+="test -r ${remote_env_q}; set -a; source ${remote_env_q}; set +a; "

if [[ -n "${REGRESSION_MAIL_REMOTE_REVISION:-}" ]]; then
    revision_q="$(quote "${REGRESSION_MAIL_REMOTE_REVISION}")"
    remote_command+="test \"\$(git rev-parse HEAD)\" = ${revision_q}; "
fi

remote_command+="export PYTHONPATH=${remote_root_q}/.deps:${remote_root_q}; "
remote_command+='export PATH="$HOME/.opencode/bin:$PATH"; '
remote_command+="exec python3 -m ngts.scripts.regression_mail"
for argument in "$@"; do
    remote_command+=" $(quote "${argument}")"
done

exec ssh "${ssh_options[@]}" "${REGRESSION_MAIL_VDI_TARGET}" "${remote_command}"
