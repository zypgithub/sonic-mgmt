#!/bin/bash

# Help function to display usage information
function show_help {
    echo "Usage: run_test.sh --setup_name=<setup_name> --test_name=<test_name>"
    echo ""
    echo "Arguments:"
    echo "  --setup_name   The setup name to be used in the pytest command"
    echo "  --test_name    The test name to be used (format: directory/test_file.py::TestClass::test_method)"
    echo "  --init         Initialize the test"
    echo "  --cleanup      Cleanup the test"
    echo "  --parameter_file_location       The location of the parameter file to be used in the pytest command"
    echo "Example:"
    echo " run_test.sh --setup_name=nv_performance_mtvr-moose-17 --test_name=switch_perf_optimizer/spcx_ra"
    exit 1
}

# Parse command line arguments
SETUP_NAME=""
TEST_NAME=""

for arg in "$@"
do
    case $arg in
        --setup_name=*)
        SETUP_NAME="${arg#*=}"
        shift
        ;;
        --test_name=*)
        TEST_NAME="${arg#*=}"
        shift
        ;;
        --init)
        INIT=true
        shift
        ;;
        --cleanup)
        CLEANUP=true
        shift
        ;;
        --parameter_file_location=*)
        PARAMETER_FILE_LOCATION="${arg#*=}"
        shift
        ;;
        --target_cli_type=*)
        TARGET_CLI_TYPE="${arg#*=}"
        shift
        ;;
        --help|-h)
        show_help
        ;;
        *)
        # Unknown option
        echo "Unknown option: $arg"
        show_help
        ;;
    esac
done

# Check if required arguments are provided
if [ -z "$SETUP_NAME" ] || [ -z "$TEST_NAME" ]; then
    echo "Error: Both --setup_name and --test_name are required"
    show_help
fi
if [ -z "$TARGET_CLI_TYPE" ]; then
    TARGET_CLI_TYPE="NVUE"
fi

# Run the pytest command

COMMAND="/ngts_venv/bin/pytest --setup_name=$SETUP_NAME \
    --rootdir=/root/mars/workspace/sonic-mgmt/ngts \
    -c /root/mars/workspace/sonic-mgmt/ngts/pytest.ini \
    --log-level=INFO \
    --clean-alluredir \
    --alluredir=/tmp/allure-results \
    --target_cli_type=$TARGET_CLI_TYPE \
    --showlocals \
    --disable_loganalyzer \
    --dynamic_update_skip_reason \
    --store_la_logs \
    --ignore_la_failure \
    --ignore-conditional-mark"

if [ "$INIT" = true ]; then
    COMMAND="$COMMAND --run_config_only"
fi

if [ "$CLEANUP" = true ]; then
    COMMAND="$COMMAND --run_cleanup_only"
fi

if [ -n "$PARAMETER_FILE_LOCATION" ]; then
    COMMAND="$COMMAND --parameter_file_location=$PARAMETER_FILE_LOCATION"
fi

COMMAND="$COMMAND /root/mars/workspace/sonic-mgmt/ngts/performance_tests/$TEST_NAME"

echo "Executing command: $COMMAND"

eval $COMMAND