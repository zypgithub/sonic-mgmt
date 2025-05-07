import os
import sys
import requests
import json
import base64
import argparse
import logging
import time
from requests.packages import urllib3
urllib3.disable_warnings()

path = os.path.abspath(__file__)
sonic_mgmt_path = path.split('/ngts/')[0]
sys.path.append(sonic_mgmt_path)

from ngts.constants.constants import InfraConst  # noqa: E402
from ngts.nvos_constants.constants_nvos import TopologyConsts

ALLURE_DOCKER_SERVICE = 'allure-docker-service'
HTTP_TIMEOUT = 300
SSL_VERIFICATION = False
PATH_TO_UPLOAD_URL = '/auto/sw_system_project/NVOS_INFRA/verification_files/'


def get_logger():
    log = logging.getLogger('AllureReporter')
    log.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    return log


logger = get_logger()


def parse_args():
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument("--action", required=True, dest="action", default="upload",
                        choices=["upload", "generate", "cleanup"], help="Action to do")
    parser.add_argument('--setup_name', dest='setup_name', help='Setup name')
    parser.add_argument('--cli_type', dest='cli_type',
                        required=False, default="", help='cli type of the OS')

    return parser.parse_args()


def upload_results(results_directory, allure_server, project_id):
    if os.path.exists(results_directory):
        create_project(allure_server, project_id)
        allure_report_items_list = collect_allure_results(results_directory)
        upload_data_to_server(allure_report_items_list, allure_server, project_id)


def create_project(allure_server_url, allure_project):
    data = {'id': allure_project}
    http_headers = {'Content-type': 'application/json'}
    url = allure_server_url + '/projects'

    if requests.get(url + '/' + allure_project, timeout=HTTP_TIMEOUT, verify=SSL_VERIFICATION).status_code != 200:
        logger.info('Creating project {} on allure server'.format(allure_project))
        response = requests.post(url, json=data, headers=http_headers, timeout=HTTP_TIMEOUT, verify=SSL_VERIFICATION)
        if response.raise_for_status():
            logger.error('Failed to create project on allure server, error: {}'.format(response.content))
    else:
        logger.info('Allure project {} already exist on server. No need to create project'.format(allure_project))


def collect_allure_results(allure_report_dir):
    allure_report_file_list = os.listdir(allure_report_dir)

    allure_report_items_list = []
    for allure_report_file_item in allure_report_file_list:
        report_item_dict = {}

        file_path = allure_report_dir + "/" + allure_report_file_item
        logger.info(file_path)

        if os.path.isfile(file_path):
            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                    if content.strip():
                        b64_content = base64.b64encode(content)
                        report_item_dict['file_name'] = allure_report_file_item
                        report_item_dict['content_base64'] = b64_content.decode('UTF-8')
                        allure_report_items_list.append(report_item_dict)
                    else:
                        logger.info('Empty File skipped: ' + file_path)
            finally:
                f.close()
        else:
            logger.info('Directory skipped: ' + file_path)

    return allure_report_items_list


def upload_data_to_server(allure_report_items_list, allure_server, project_id):
    headers = {'Content-type': 'application/json'}
    request_body = {
        "results": allure_report_items_list
    }
    json_request_body = json.dumps(request_body)

    logger.info("------------------SEND-RESULTS------------------")
    start_time = time.time()
    send_result_url = '{}/send-results?project_id={}'.format(allure_server, project_id)
    diff_time = time.time() - start_time
    logger.info(f"uploading data takes {diff_time}")
    response = requests.post(send_result_url, headers=headers, data=json_request_body, verify=SSL_VERIFICATION,
                             timeout=HTTP_TIMEOUT)
    logger.info("STATUS CODE:")
    logger.info(response.status_code)


def store_allure_url(allure_project, report_url):
    try:
        if TopologyConsts.NVOS.lower() in allure_project.lower():
            logger.info("Upload url path to file")
            file_path = os.path.join(PATH_TO_UPLOAD_URL, f"{allure_project}.txt")
            with open(file_path, "w") as f:
                f.write(report_url)
            logger.info(f"File {file_path} created")
            with open(file_path, "r") as f:
                content = f.read()
            logger.info(f"Contents of {file_path}:\n{content}")
    except BaseException as ex:
        logger.warning(f"Failed to store allure url for NVOS ({ex})")


def generate_report(allure_server_url, allure_project):
    allure_report_url = predict_allure_report_link(allure_server_url, allure_project)
    store_allure_url(allure_project, allure_report_url)

    start_time = time.time()
    response = requests.get('{}/generate-report?project_id={}'.format(allure_server_url, allure_project),
                            verify=SSL_VERIFICATION, timeout=HTTP_TIMEOUT).json()
    diff_time = time.time() - start_time
    logger.info(f"generating report takes {diff_time}")
    report_url = response['data']['report_url']
    logger.info('Allure report URL: {}'.format(report_url))

    cleanup_report(allure_server_url, allure_project)


def predict_allure_report_link(allure_server_url, allure_project):
    """
    THe function is to construct allure report link base on the current allure report index.
     The new allure report index is equal to the current index + 1
    """
    allure_report_url = None
    try:
        response = requests.get('{}/projects/{}'.format(allure_server_url, allure_project),
                                verify=SSL_VERIFICATION, timeout=HTTP_TIMEOUT).json()
        allure_report_index = int(response['data']['project']["reports_id"][1]) + 1 \
            if len(response['data']['project']["reports_id"]) > 1 else 1

        allure_report_url = "{}/projects/{}/reports/{}/index.html".format(
            allure_server_url, allure_project, allure_report_index)
    except Exception as err:
        logger.error("Fail to construct allure report url. Err:{}".format(err))
    else:
        logger.info("\n\n\n When allure report size it too bigger, generating allure report usually timeouts"
                    "\n To avoid missing allure report link"
                    "\n We construct the allure report link base current report index before generating allure report"
                    "\n Predict Allure report URL:{} \n\n\n".format(allure_report_url))
    return allure_report_url


def cleanup_report(allure_server_url, allure_project):
    requests.get('{}/clean-results?project_id={}'.format(allure_server_url, allure_project),
                 verify=SSL_VERIFICATION, timeout=HTTP_TIMEOUT)


if __name__ == "__main__":
    args = parse_args()

    allure_report_dir = InfraConst.ALLURE_REPORT_DIR
    allure_server_addr = InfraConst.ALLURE_SERVER_URL
    setup_name = args.setup_name
    cli_type = args.cli_type
    cli_type_str = f"-{cli_type}" if cli_type else ""
    allure_project_id = (setup_name.replace('_', '-') + cli_type_str).lower() + "-session-reports"
    allure_server_base_url = '{}/{}'.format(allure_server_addr, ALLURE_DOCKER_SERVICE)

    if args.action == 'upload':
        upload_results(allure_report_dir, allure_server_base_url, allure_project_id)
    if args.action == 'generate':
        generate_report(allure_server_base_url, allure_project_id)
    if args.action == 'cleanup':
        cleanup_report(allure_server_base_url, allure_project_id)
