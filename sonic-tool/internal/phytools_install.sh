#!/bin/bash
 
# please visit https://confluence.nvidia.com/display/SW/How+to+automatically+install+phytools+container+to+SONiC
# for more information

SWITCH_ADDRESS=""
PASSWORD="YourPaSsWoRd"
 
LOCAL_IP=$(hostname -I | awk '{print $1}')
 
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --switch_address)
            SWITCH_ADDRESS="$2"
            shift 2
            ;;
        --password)
            PASSWORD="$2"
            shift 2
            ;;
        *)
            echo "Unknown parameter passed: $1"
            exit 1
            ;;
    esac
done
 
if [ -z "$SWITCH_ADDRESS" ]; then
    echo "Usage: $0 --switch_address <HOST> [--password <PASSWORD>]"
    exit 1
fi
 
xhost +
 
echo "Target Address: $SWITCH_ADDRESS"
echo "Password: $PASSWORD"
 
sshpass -p "$PASSWORD" ssh -X admin@$SWITCH_ADDRESS << EOF
sudo apt-get update
sudo apt-get install -y xauth x11-utils x11-apps
docker run -i --rm -h phytools \
    -v /tmp/:/tmp_1/:rw \
    -v /dev/mst:/dev/mst \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -e DISPLAY=\$DISPLAY \
    --device=/dev/mst \
    --name phytools \
    --privileged \
    --net=host \
    harbor.mellanox.com/phytools/phytools bash -c "
    export DISPLAY=$LOCAL_IP:1
    echo 'DISPLAY set to $LOCAL_IP:1'
    /tmp/nvidia/phy_monitor.py"
EOF
