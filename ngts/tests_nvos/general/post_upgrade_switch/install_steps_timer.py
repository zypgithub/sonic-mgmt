import io
import json
import logging
import time
from collections import OrderedDict
from typing import Optional

# Configuration
JSON_FILE_PATH = "/tmp/timing_intervals.json"


class InstallStepsTimer:

    @classmethod
    def initialize_timer(cls) -> None:
        """
        Initialize the JSON file. If it exists, clear it.
        If it doesn't exist, create a new empty file.
        """
        with open(JSON_FILE_PATH, 'w') as f:
            json.dump({}, f)
        logging.info(f"Initialized empty JSON file at {JSON_FILE_PATH}")

    @classmethod
    def add_timestamp(cls, key: str, override_if_exists=False) -> None:
        """
        Add a timestamp for the given key to the JSON file.
        If the key already exists, append "-1" to the end of the key.
        """
        logging.info(f'Saving timestamp for step: "{key}"')

        try:
            with open(JSON_FILE_PATH, 'r+') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = {}

                if override_if_exists:
                    data[key] = time.time()
                else:
                    original_key = key
                    counter = 1
                    while key in data:
                        key = f"{original_key}-{counter}"
                        counter += 1

                    data[key] = time.time()

                f.seek(0)
                json.dump(data, f, indent=4)
                f.truncate()
        except IOError as e:
            logging.info(f"Error accessing the JSON file: {e}")

    @classmethod
    def get_timestamp(cls, key: str) -> Optional[float]:
        """
        Retrieve the timestamp for a given key.
        Returns None if the key doesn't exist.
        """
        try:
            with open(JSON_FILE_PATH, 'r') as f:
                data = json.load(f)
                return data.get(key)
        except (IOError, json.JSONDecodeError) as e:
            logging.info(f"Error reading the JSON file: {e}")
            return None

    @classmethod
    def calculate_interval(cls, start_key: str, end_key: str) -> Optional[float]:
        """
        Calculate the time interval between two keys.
        Returns None if either key doesn't exist.
        """
        start_time = cls.get_timestamp(start_key)
        end_time = cls.get_timestamp(end_key)

        if start_time is not None and end_time is not None:
            return end_time - start_time
        else:
            return None

    @classmethod
    def print_saved_timestamps(cls):
        """
        Print the content of the JSON file, ordered by timestamp.
        """
        try:
            with open(JSON_FILE_PATH, 'r') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    logging.info("The JSON file is empty or contains invalid data.")
                    return

            # Sort the data by timestamp
            sorted_data = OrderedDict(sorted(data.items(), key=lambda x: x[1]))

            logging.info("Timestamps ordered by time:")
            logging.info("-" * 40)
            for key, timestamp in sorted_data.items():
                # Convert timestamp to a readable format
                readable_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
                logging.info(f"{key}: {readable_time}")
            logging.info("-" * 40)

        except IOError as e:
            logging.info(f"Error accessing the JSON file: {e}")

    @classmethod
    def analyze_saved_timestamps(cls) -> str:
        """
        Read the JSON file, create two ordered dictionaries:
        1. Timestamps ordered by their value
        2. Intervals between sequential timestamps
        Then log the output using logging.info and return it as a string.
        Handle the case where the file is empty or contains no timestamps.
        """
        output = io.StringIO()

        try:
            with open(JSON_FILE_PATH, 'r') as f:
                data = json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            error_msg = f"Error reading the JSON file: {e}"
            logging.error(error_msg)
            return error_msg

        if not data:
            message = "No timestamps found in the file."
            logging.info(message)
            return message

        # Create an ordered dict of timestamps
        timestamps = OrderedDict(sorted(data.items(), key=lambda x: x[1]))

        # Create an ordered dict of intervals
        intervals = OrderedDict()
        keys = list(timestamps.keys())
        for i in range(len(keys) - 1):
            from_key, to_key = keys[i], keys[i + 1]
            interval = timestamps[to_key] - timestamps[from_key]
            interval_key = f"from {from_key} to {to_key}"
            intervals[interval_key] = interval

        # Capture timestamps
        print("Ordered Timestamps:", file=output)
        print("-" * 40, file=output)
        for key, value in timestamps.items():
            readable_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(value))
            print(f"{key}: {readable_time}", file=output)
        print("-" * 40, file=output)

        # Capture intervals
        if intervals:
            print("\nOrdered Intervals:", file=output)
            print("-" * 40, file=output)
            for key, value in intervals.items():
                print(f"{key}: {value:.2f} seconds", file=output)
            print("-" * 40, file=output)
        else:
            print("\nNo intervals to display (less than two timestamps).", file=output)

        # Get the entire output as a string
        full_output = output.getvalue()

        # Log the full output
        logging.info("\n" + full_output)

        return full_output
