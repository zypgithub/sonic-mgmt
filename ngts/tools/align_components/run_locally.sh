#!/bin/bash
set -e

if [ $# -ne 2 ]; then
    echo "Example: $0 <hostname> <fwpkg_path>"
    echo "Example: $0 juliet-154 --erot_path=erot.fwpkg"
    exit 1
fi

hostname=$1
fwpkg_path=$2
res=$(curl -s --location https://noga.mellanox.com/app/server/php/rest_api?api_cmd=get_resource_data\&resource_name=$hostname)
if [ $? -ne 0 ]; then
  echo "Curl command failed" >&2
  exit 1
fi
setup_name=$(echo $res | jq -r '.data.relations."associated with"[0].NAME')
python3 /auto/sw_system_project/NVOS_INFRA/verification_files/platform_components/align_components/align_fw_components.py --setup_name=$setup_name $fwpkg_path
