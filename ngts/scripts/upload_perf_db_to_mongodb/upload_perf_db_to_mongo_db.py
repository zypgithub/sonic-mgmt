#!/usr/bin/env python
import allure
import logging
import pytest
import shutil
import os
import json
from datetime import datetime
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts

logger = logging.getLogger()


@pytest.mark.disable_loganalyzer
@allure.title('Upload Performance Database into MongoDB')
def test_upload_perf_db():
    try:
        lines = [MongoDbConsts.COLLECTION, MongoDbConsts.CRITERIA]
        destination_path = MongoDbConsts.MONGO_DB_UPLOADS
        for root, dirs, files in os.walk(PerfConsts.REQUIRMENTS_DIR):
            for file in files:
                if file.endswith('_info_dump.json'):
                    test_info_path = os.path.join(root, file)
                    with open(test_info_path, "r+") as f:
                        test_specific_values = json.load(f)
                        test_specific_values_str = json.dumps(test_specific_values) + "\n"
                        lines.append(test_specific_values_str)
        time_now = datetime.now().strftime(MongoDbConsts.TIME_REGEX_FORMAT_FOR_MONGO_DB)
        final_mongo_db_results_path = os.path.join(PerfConsts.REQUIRMENTS_DIR, f'switch_perf_db_{time_now}.db')
        with open(final_mongo_db_results_path, 'w') as file:
            file.writelines(lines)
        shutil.copy(final_mongo_db_results_path, destination_path)
    except Exception as err:
        raise AssertionError(err)
