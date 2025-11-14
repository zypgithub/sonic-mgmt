#!/bin/bash
export PYTHONPATH=/local/remote/sonic/sonic-mgmt:$PYTHONPATH
echo "=========================================================================="
echo "|                         Welcome to AirSpin!                            |"
echo "|                           version: 1.0.0                               |"
echo "| Manual: https://confluence.nvidia.com/display/SW/AirSpin+documentation |"
echo "=========================================================================="

show_help() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  help,          Show this help message and exit"
    echo "  create,        Create a new air simulation"
    echo "  list,          List all air simulations of the current user"
}

# No args case
if [ $# -eq 0 ]; then
    show_help
    exit 1
fi

AIRSPIN_PYTHON_ENV=/auto/sw_regression/system/SONIC/airspin/venv/bin/python

handle_create(){
    $AIRSPIN_PYTHON_ENV ngts/scripts/air_spin/cli.py create $@
}

handle_list(){
    $AIRSPIN_PYTHON_ENV ngts/scripts/air_spin/cli.py list $@
}

case $1 in
    create)
        shift
        handle_create $@
        ;;
    list)
        shift
        handle_list $@
        ;;
    *)
        show_help
        exit 0
        ;;
esac
