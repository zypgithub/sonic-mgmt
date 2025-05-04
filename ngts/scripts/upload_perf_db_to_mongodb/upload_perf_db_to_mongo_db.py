#!/usr/bin/env python
import allure
import logging
import pytest
import shutil
import time
import os
import json
from datetime import datetime
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts

logger = logging.getLogger()


@pytest.mark.disable_loganalyzer
@allure.title('Upload Performance Database into MongoDB')
def test_upload_perf_db(topology_obj):
    try:
        with open(MongoDbConsts.PERF_MONGO_DB_RESULTS_PATH, "r+") as f:
            dut_system_information_template_json = json.load(f)
        lines = [MongoDbConsts.COLLECTION, MongoDbConsts.CRITERIA]
        tests_path_specific_values_dict = {}
        destination_path = MongoDbConsts.MONGO_DB_UPLOADS
        for root, dirs, files in os.walk(PerfConsts.REQUIRMENTS_DIR):
            for file in files:
                if file.endswith('_info_dump.json'):
                    test_info_path = os.path.join(root, file)
                    with open(test_info_path, "r+") as f:
                        test_specific_values = json.load(f)
                        dut_system_information_template_json.update({'result': test_specific_values})
                        test_specific_values_str = json.dumps(dut_system_information_template_json) + "\n"
                        tests_path_specific_values_dict[test_info_path] = test_specific_values_str
        passing_sandbox_validation_tests, failing_sandbox_validation_tests = do_sandbox_testing(tests_path_specific_values_dict, topology_obj)
        for test_path in passing_sandbox_validation_tests:
            lines.append(tests_path_specific_values_dict[test_path])
        time_now = datetime.now().strftime(MongoDbConsts.TIME_REGEX_FORMAT_FOR_MONGO_DB)
        final_mongo_db_results_path = os.path.join(PerfConsts.REQUIRMENTS_DIR, f'switch_perf_db_{time_now}.db')
        logger.info(f"Writing final mongo db results to {final_mongo_db_results_path}")
        with open(final_mongo_db_results_path, 'w') as file:
            file.writelines(lines)
        logger.info(f"Copying final mongo db results to {destination_path}")
        shutil.copy(final_mongo_db_results_path, destination_path)
        if failing_sandbox_validation_tests:
            raise AssertionError(f"Tests {failing_sandbox_validation_tests} failed sandbox validation")
    except Exception as err:
        raise AssertionError(err)


def do_sandbox_testing(tests_path_specific_values_dict, topology_obj):
    hyper_engine = topology_obj.players['hypervisor']['engine']
    logger.info("Starting sandbox testing")
    passing_sandbox_validation_tests = []
    failing_sandbox_validation_tests = []
    for test_path, test_specific_values_str in tests_path_specific_values_dict.items():
        test_name = os.path.basename(test_path)
        updated_test_name = test_name.replace("-", "_").replace(" ", "_").replace("[", "_").replace("]", "_")
        lines = [MongoDbConsts.COLLECTION, MongoDbConsts.CRITERIA, test_specific_values_str]
        test_db_sandbox_testing_path = os.path.join(MongoDbConsts.MONGO_DB_SANDBOX_TESTS, f"{updated_test_name}.db")
        logger.info(f"Writing test {test_name} to sandbox testing file")
        with open(test_db_sandbox_testing_path, 'w') as file:
            file.writelines(lines)
        logger.info("Running sandbox testing")
        hyper_engine.run_cmd(MongoDbConsts.MONGO_DB_SANDBOX_TESTING_COMMAND)
        time.sleep(MongoDbConsts.MONGO_DB_SANDBOX_TESTING_TIMEOUT)
        logger.info("Sandbox testing finished")
        logger.info("Checking if the test failed sandbox validation")
        test_db_sandbox_testing_err_path = os.path.join(MongoDbConsts.MONGO_DB_SANDBOX_TESTS, f"{updated_test_name}.err")
        err_file_exists = os.path.exists(test_db_sandbox_testing_err_path)
        if err_file_exists:
            failing_sandbox_validation_tests.append(test_path)
            logger.error(f"Test {test_path} failed sandbox validation")
            os.remove(test_db_sandbox_testing_err_path)
        else:
            passing_sandbox_validation_tests.append(test_path)
            logger.info(f"Test {test_path} passed sandbox validation")
        os.remove(test_db_sandbox_testing_path)
    return passing_sandbox_validation_tests, failing_sandbox_validation_tests
