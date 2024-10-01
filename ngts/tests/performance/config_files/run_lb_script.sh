#!/bin/bash

set -x

# Check if log port argument is provided
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <initial_hex_value> <iterations number>"
    exit 1
fi

# Initialize log port with the provided argument
X=$1

iterations=$2

if [ $iterations -eq 128 ]; then
        jump=1
    elif [ $iterations -eq 64 ]; then
        jump=2
    else
        echo "Error: The ports number must be 64 or 128."
        exit 1
    fi

check_rc()
{
  rc=$?
  if  [ $rc -ne 0 ]; then
    echo "$1";
    exit $1;
  fi
}

cat /tmp/sai.profile | grep SAI_INDEPENDENT_MODULE_MODE=1
if  [ $? -eq 0 ]; then
  im_enabled=1
  else
  im_enabled=0
fi
echo $im_enabled
# Run the loop 64 times
for (( i=0; i<$iterations; i++ )); do
    # Convert X to hexadecimal string
    hex_X=$(printf '%#x' "$X")

    # Run the command with updated value of X
    yes y | sx_api_port_state_set.py --log_port "$hex_X" --state down
    check_rc  'ERROR: Shutting down the port has failed' 1
    sx_api_port_phys_loopback.py --cmd 0 --log_port "$hex_X" --loopback_type 2 --force
    check_rc  'ERROR: Setting loopback on the port has  failed' 1
    python api_for_filter.py --log_port "$hex_X"
    check_rc  'ERROR: Setting loopback filter on the port has failed' 1
    if [ $im_enabled -eq 1 ]; then
      echo "IM mode, setting tx signal and setting port rate"
      port_rate=$(/usr/bin/sx_api_port_rate_get.py --log_port  "$hex_X" | grep "Port admin rate" | awk '{print $5}' | tr -d "[]'\\\\")

      check_rc  'ERROR: Getting the port rate  has failed' 1
      yes y | sx_api_port_tx_signal_set.py --log_port "$hex_X"  --state up
      check_rc  'ERROR: Setting tx signal  has failed' 1
      yes y | sx_api_port_rate_set.py --log_port "$hex_X" --rate "$port_rate"
      check_rc  'ERROR: Setting port rate  has failed' 1
    fi
    yes y | sx_api_port_state_set.py --log_port "$hex_X" --state up
    check_rc  'ERROR: Starting up the port has failed' 1

    ((X+=$jump))
done
