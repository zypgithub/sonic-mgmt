#!/usr/bin/env bash

RED="\033[1;31m"
NC="\033[0m"
SELF_NAME=$(basename "$0")
VERBOSITY=1
RELATIVE_PATH_TO_CONSTANTS="sonic-tool/mars/scripts/lib/constants.py"
BASEDIR=$(dirname $0)
PATH_TO_CONSTANTS="${BASEDIR}/../../../${RELATIVE_PATH_TO_CONSTANTS}"

################################
#                              #
# Script configuration section #
#                              #
################################
USAGE(){
    cat << EOF

${SELF_NAME}

Info:
     The script will print the NGTS version of a given sonic-mgmt repo
EOF
}

error(){
    if [[ ${VERBOSITY} -gt 0 ]]; then
        echo -e "${RED}[ERROR] $1${NC}"; exit 1
    fi
}

# Verify that file exists #
if [ ! -f "$PATH_TO_CONSTANTS" ]; then
    error "Upstream script RC=1 $PATH_TO_CONSTANTS does not exists."
fi

# Extract NGTS version from the constants file #
NGTS_VERSION=$(sed -nE 's/^[[:space:]]*DOCKER_NGTS_DEFAULT_TAG[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' "$PATH_TO_CONSTANTS" | head -n 1)

# Verify that NGTS version isn't empty #
if [ -z "$NGTS_VERSION" ]; then
    error "Upstream script RC=1. Unable to extract the NGTS version from the constants.py file"
fi

echo "$NGTS_VERSION"
exit 0
