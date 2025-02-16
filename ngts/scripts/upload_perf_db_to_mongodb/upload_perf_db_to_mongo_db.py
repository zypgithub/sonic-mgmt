#!/usr/bin/env python
import allure
import logging
import pytest
import shutil
import os
import json
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts

logger = logging.getLogger()


@pytest.mark.disable_loganalyzer
@allure.title('Upload Performance Database into MongoDB')
def test_upload_perf_db(players, setup_name):
    try:
        lines = [MongoDbConsts.COLLECTION, MongoDbConsts.CRITERIA]
        destination_path = MongoDbConsts.MONGO_DB_UPLOADS
        for root, dirs, files in os.walk(PerfConsts.REQUIRMENTS_DIR):
            for file in files:
                if file.endswith('_info_dump.json'):
                    test_info_path = os.path.join(root, file)
                    with open(test_info_path, "r+") as f:
                        test_specific_values = json.load(f)
                        test_specific_values_str = json.dumps(test_specific_values)
                        lines.append(test_specific_values_str + "\n")
        with open(MongoDbConsts.PERF_MONGO_DB_RESULTS_PATH, 'w') as file:
            file.writelines(lines)
        shutil.copy(MongoDbConsts.PERF_MONGO_DB_RESULTS_PATH, destination_path)
    except Exception as err:
        raise AssertionError(err)
