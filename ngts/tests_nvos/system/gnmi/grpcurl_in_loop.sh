#!/bin/bash

date
echo "Execution started."

CACERT=$1
USER=$2
PASSWORD=$3

# Command to run
COMMAND="grpcurl -cacert $CACERT -H username:$USER -H password:$PASSWORD nvos-dut:9339 describe"

# Strings to search for (can be multiple)
STRINGS=("failed to verify certificate" "Failed" "failed")

# Function to check if any of the strings are present in the output
check_strings() {
    local output="$1"
    for str in "${STRINGS[@]}"; do
        if [[ "$output" == *"$str"* ]]; then
            return 0  # String found
        fi
    done
    return 1  # No strings found
}

# Main loop
while true; do
    # Run the command and capture both stdout and stderr
    echo "$COMMAND"
    OUTPUT=$($COMMAND 2>&1)

    # Print the output
    echo "$OUTPUT"

    # Check if any of the strings are in the output
    if ! check_strings "$OUTPUT"; then
        # If none of the strings are found, break the loop
        echo "None of the specified strings were found in the output."
        break
    fi

#    sleep 0.5
done

date
echo "Execution completed."