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
