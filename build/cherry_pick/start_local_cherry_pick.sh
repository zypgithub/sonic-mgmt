#!/bin/bash


GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

CONTAINER_NAME="sonic-mgmt-cherry-pick"

set -e

print_usage() {
    echo "Usage: $0 <GERRIT_API_TOKEN> <GERRIT_USERNAME>"
    echo "    GERRIT_API_TOKEN: the gerrit api token"
    echo "    GERRIT_USERNAME: the gerrit username. Default is svc_sonic_ver_bot"
    echo "Example: $0 1234567890 svc_sonic_ver_bot"
    echo "Example: $0 1234567890"
    exit 0
}

print_summary() {
    echo -e "${GREEN}${CONTAINER_NAME} container is running${NC}"
    echo -e "${BLUE}You can execute cherry pick by running the following command:${NC}"
    echo "docker exec -it ${CONTAINER_NAME} bash"
    echo -e "${BLUE}Sample command to cherry pick:${NC}"
    echo "python main.py --loglevel DEBUG --since \"2025-03-01\" --until=\"now\" \\"
    echo "  --recipients your_mail@nvidia.com --branch 202411 \\"
    echo "  --repo_path /root/sonic-mgmt --no-reset"
}

if [ -z "$1" -o "$1" = "help" -o "$1" = "-h" -o "$1" = "--help" ]; then
    print_usage
fi

GERRIT_API_TOKEN=$1
GERRIT_USERNAME="svc_sonic_ver_bot"

if [ -n "$2" ]; then
    GERRIT_USERNAME=$2
fi

code_dir=$(cd $(dirname $0); pwd)

BUILDKIT_PROGRESS=plain docker build -f ${code_dir}/Dockerfile -t sonic-mgmt-cherry-pick \
    --build-arg GERRIT_API_TOKEN=${GERRIT_API_TOKEN} \
    --build-arg GERRIT_USERNAME=${GERRIT_USERNAME} \
    ${code_dir}

if [ "$(docker ps -a -q -f name=^${CONTAINER_NAME}$)" ]; then
    echo -e "${BLUE}Cherry pick container already exists, remove it? (y/n)${NC}"
    read -p "Enter: " choice
    if [ "${choice}" = "y" ]; then
        echo -e "${GREEN}Removing cherry pick container${NC}"
        docker rm -f ${CONTAINER_NAME}
    else
        print_summary
        exit 0
    fi
fi

echo -e "${GREEN}Starting cherry pick container${NC}"
docker run -idt --name ${CONTAINER_NAME} \
    sonic-mgmt-cherry-pick bash
print_summary
