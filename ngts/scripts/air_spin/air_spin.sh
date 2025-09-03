#!/bin/bash
export PYTHONPATH=/local/remote/sonic/sonic-mgmt:$PYTHONPATH

show_help() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -h, --help     Show this help message and exit"
    echo "  -v, --version  Show version information and exit"
    echo "  -c, --create   Create a new air simulation"
    echo "  -s, --start    Start an existing air simulation"
    echo "  -d, --destroy  Destroy an existing air simulation"
}

# No args case
if [ $# -eq 0 ]; then
    show_help
    exit 1
fi

handle_create(){
    python3 ngts/scripts/air_spin/cli.py create $@
}

case $1 in
    create)
        shift
        handle_create $@
        ;;
    *)
        show_help
        exit 1
        ;;
esac
