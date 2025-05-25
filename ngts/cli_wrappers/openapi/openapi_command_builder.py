import json
import logging
import time
from typing import Tuple

import requests
from requests.auth import HTTPBasicAuth
from retry import retry

from ngts.nvos_constants.constants_nvos import OpenApiReqType, NvosConst, SystemConsts
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()

ENDPOINT_URL_TEMPLATE = 'https://{ip}:{port_num}/nvue_v1'
REQ_HEADER = {"Content-Type": "application/json"}
SSL_ERRORS = ['No required SSL certificate was sent']
ERRORS_TO_RETRY_APPLY_CHECK = ['Internal Server Error', 'Authentication service temporarily unavailable.']
INVALID_RESPONSE = ['Unauthorized', "ays_fail", "invalid", "Bad Request", "Not Found", "Forbidden", 'The requested item does not exist.'] + ERRORS_TO_RETRY_APPLY_CHECK + SSL_ERRORS
PENDING_RESPONSE = "pending"
APPLIED_RESPONSES = ["applied", "applied_and_saved"]


class RequestData:
    user_name = ''
    password = ''
    endpoint_ip = ''
    resource_path = ''
    param_name = None
    param_value = None

    def __init__(self, user_name, password, endpoint_ip, resource_path, param_name, param_value):
        self.user_name = user_name
        self.password = password
        self.endpoint_ip = endpoint_ip
        self.resource_path = resource_path
        self.param_name = param_name
        self.param_value = param_value


class OpenApiRequest:
    payload = {}
    changeset = None
    port_num = "443"
    client_certs: CertInfo = None

    @staticmethod
    def print_request(r: requests.PreparedRequest, req_data: RequestData):
        output = f"\n=======Request=======\ncurl -k --user {req_data.user_name}:***** \\\n"
        if r.headers:
            output += "  " + ' '.join(f"-H '{k}: {v}'" for k, v in r.headers.items()) + " \\\n"
        output += f"  --request {r.method} {r.url} "
        if r.body:
            output += f"\\\n  -d '{OpenApiRequest.format_json_str(json.dumps(r.body))}'"
        output += "\n====================="
        logger.info(output)

    @staticmethod
    def print_response(r: requests.Response, req_type):
        if req_type == OpenApiReqType.ACTION and getattr(r, 'text', ''):
            response = r.text
        elif getattr(r, 'text', '').startswith('<html>'):
            response = r.text
        else:
            response = json.dumps(r.json(), indent=2) if req_type in [OpenApiReqType.PATCH, OpenApiReqType.GET] else r.content
        output = f'\n' \
            f'=======Response=======\n' \
            f'{OpenApiRequest.format_json_str(response)}\n' \
            f'======================'
        logger.info(output)

    @staticmethod
    def format_json_str(s):
        if isinstance(s, bytes):
            s = s.decode('utf-8')
        if s.startswith('"'):
            s = s[1:]
        if s.endswith('"'):
            s = s[:-1]
        s = s.replace('\\"', '"').replace('\\n', '\n')
        return s or '{}'

    @staticmethod
    def _get_endpoint_url(request_data):
        server_addr = OpenApiRequest.client_certs.dn if OpenApiRequest.client_certs else request_data.endpoint_ip
        return ENDPOINT_URL_TEMPLATE.format(ip=server_addr, port_num=OpenApiRequest.port_num)

    @staticmethod
    def _get_http_auth(request_data):
        return HTTPBasicAuth(username=request_data.user_name, password=request_data.password)

    @staticmethod
    def create_nvue_changest(request_data):
        req_type = 'POST'
        with allure.step(f"Send {req_type} request to create NVUE change-set"):
            logging.info(f"Send {req_type} request to create NVUE change-set")
            r = requests.post(url=OpenApiRequest._get_endpoint_url(request_data) + "/revision",
                              auth=OpenApiRequest._get_http_auth(request_data), **OpenApiRequest._get_client_security_config())
            OpenApiRequest.print_request(r.request, request_data)
            OpenApiRequest.print_response(r, req_type)

            validation_res = OpenApiRequest._validate_response(r, req_type)
            if not validation_res.result:
                return validation_res

            response = r.json()
            OpenApiRequest.changeset = response.popitem()[0]

            logging.info("Using NVUE change-set: '{}'".format(OpenApiRequest.changeset))

            return validation_res

    @staticmethod
    def clear_changeset_and_payload():
        OpenApiRequest.changeset = None
        OpenApiRequest.payload = {}

    @staticmethod
    def apply_nvue_changeset(request_data, op_param_name, add_approve=True, client_certs_after_apply: CertInfo = None):
        res = OpenApiRequest._config_diff(request_data)
        if not res.result:
            return res.info
        res = OpenApiRequest._apply_config(request_data, add_approve, client_certs_after_apply)
        OpenApiRequest.clear_changeset_and_payload()
        res.ignore_result()
        return res.info

    @staticmethod
    def _config_diff(request_data):
        with allure.step("Config diff"):
            logging.info("Config diff")
            params = {
                'rev': OpenApiRequest.changeset,
                'filled': 'False',
                'diff': 'applied'
            }
            r = requests.get(url=f'{OpenApiRequest._get_endpoint_url(request_data)}/', params=params,
                             auth=OpenApiRequest._get_http_auth(request_data), **OpenApiRequest._get_client_security_config())
            OpenApiRequest.print_request(r.request, request_data)
            OpenApiRequest.print_response(r, OpenApiReqType.PATCH)
            return OpenApiRequest._validate_response(r, OpenApiReqType.PATCH)

    @staticmethod
    def _apply_config(request_data, add_approve, client_certs_after_apply: CertInfo = None):
        with allure.step("Apply NVUE change-set"):
            logging.info("Apply NVUE change-set")
            apply_payload = {"state": "apply", "auto-prompt": {"ays": "ays_yes"}} if add_approve else {"state": "apply"}
            url = '{url_end_point}/revision/{req_quote}'.format(
                url_end_point=OpenApiRequest._get_endpoint_url(request_data),
                req_quote=requests.utils.quote(OpenApiRequest.changeset, safe=""))
            r = requests.patch(url=url, auth=OpenApiRequest._get_http_auth(request_data),
                               data=json.dumps(apply_payload), headers=REQ_HEADER, **OpenApiRequest._get_client_security_config())
            OpenApiRequest.print_request(r.request, request_data)
            OpenApiRequest.print_response(r, OpenApiReqType.PATCH)
            OpenApiRequest._validate_response(r, OpenApiReqType.PATCH)

            try:
                time.sleep(1)
                result = OpenApiRequest._check_apply_status(request_data, OpenApiRequest.changeset, client_certs_after_apply)
                if result.result:
                    result.info = "Configuration applied successfully"
            except Exception:
                result = ResultObj(False, "Error: Failed to apply configuration")
            finally:
                OpenApiRequest.changeset = None
                OpenApiRequest.payload = {}
                return result

    @staticmethod
    def _get_client_security_config() -> dict:
        if OpenApiRequest.client_certs:
            return {
                'verify': OpenApiRequest.client_certs.cacert,
                'cert': (OpenApiRequest.client_certs.public, OpenApiRequest.client_certs.private)
            }
        else:
            return {'verify': False}

    @staticmethod
    @retry(Exception, tries=15, delay=3)
    def _check_apply_status(request_data, changeset, client_certs_after_apply: CertInfo = None):
        with allure.step("Check the status of the apply"):
            logging.info("Check the status of the apply")
            req_url = '{url_endpoint}/revision/{req_quote}'.format(
                url_endpoint=OpenApiRequest._get_endpoint_url(request_data),
                req_quote=requests.utils.quote(changeset, safe=""))
            r = requests.get(url=req_url, auth=OpenApiRequest._get_http_auth(request_data), **OpenApiRequest._get_client_security_config())
            OpenApiRequest.print_request(r.request, request_data)
            OpenApiRequest.print_response(r, OpenApiReqType.GET)
            res = OpenApiRequest._validate_response(r, OpenApiReqType.GET)
            if not res.result:
                assert all(err not in res.info for err in ERRORS_TO_RETRY_APPLY_CHECK), res.info
                if any(err in res.info for err in SSL_ERRORS):
                    OpenApiRequest.update_client_certs_info(client_certs_after_apply)
                    raise ValueError(res.info)
                return res.info

            obj = json.loads(r.content)

            if "state" in obj.keys():
                if obj["state"] in APPLIED_RESPONSES:
                    return ResultObj(True, "Configuration applied successfully")
                if str(obj["state"]) in INVALID_RESPONSE:
                    logging.info("Apply state: " + str(obj["state"]))
                    try:
                        msg = obj["transition"]['issue']['00000']["message"]
                    except BaseException:
                        msg = ""
                    return ResultObj(False, "Error: Failed to apply configuration. Reason: " + msg)
                if obj["state"] == PENDING_RESPONSE:
                    try:
                        msg = obj["transition"]['issue']['00000']["message"]
                        if NvosConst.NO_CONFIG_DIFF_APPLY_MSG in str(msg):
                            return ResultObj(True, NvosConst.NO_CONFIG_DIFF_APPLY_MSG)
                    except BaseException:
                        raise Exception("Configuration status in pending")
                else:
                    raise Exception("Waiting for configuration to be applied")

    @staticmethod
    def update_client_certs_info(client_certs: CertInfo):
        OpenApiRequest.client_certs = client_certs

    @staticmethod
    def _create_json_payload(resource, param):
        if len(resource) > 0:
            key = resource.pop(0)
            dictionary = {key: OpenApiRequest._create_json_payload(resource, param)}
        else:
            dictionary = param
        return dictionary

    @staticmethod
    def _check_html_response(r: requests.Response) -> ResultObj:
        if getattr(r, 'text', '').startswith('<html>'):
            response = r.text
            response_first_lines = "".join(response.split('\n')[:4])
            if any(msg in response_first_lines for msg in INVALID_RESPONSE):
                return ResultObj(False, "Error: Request failed. Details:\n" + response)
        return ResultObj(True, "")

    @staticmethod
    def _check_action_post_response(r: requests.Response) -> ResultObj:
        html_check_res = OpenApiRequest._check_html_response(r)
        if not html_check_res.result:
            return html_check_res
        if any(err_str in getattr(r, 'text', '') for err_str in ['Bad Request', '400', 'Error', 'error']):
            return ResultObj(False, r.text, None)
        return ResultObj(True, 'post request succeeded')

    @staticmethod
    def _validate_response(r: requests.Response, req_type):
        res = OpenApiRequest._check_html_response(r)
        if not res.result:
            return res
        if req_type == OpenApiReqType.DELETE:
            if r.status_code != 204:
                return ResultObj(False, f"Error. Response code is: {r.status_code}, instead of 204")
        else:
            if req_type == OpenApiReqType.PATCH:
                response = r.json()
            else:
                response = json.loads(r.content)
            if 'title' in response.keys() and response['title'] in INVALID_RESPONSE:
                return ResultObj(False, "Error: Request failed. Details: " + response['detail'])
        return ResultObj(True, "")

    @staticmethod
    def send_get_request(request_data, op_params=''):
        with allure.step('Send GET request'):
            logging.info("Send GET request")
            params = '' if not op_params else op_params if op_params.startswith('?') else "/" + op_params
            req_url = '{url}{resource_path}{params}'.format(url=OpenApiRequest._get_endpoint_url(request_data),
                                                            params=params,
                                                            resource_path=request_data.resource_path)
            r = requests.get(url=req_url, auth=OpenApiRequest._get_http_auth(request_data), **OpenApiRequest._get_client_security_config())
            OpenApiRequest.print_request(r.request, request_data)
            OpenApiRequest.print_response(r, OpenApiReqType.GET)

            res = OpenApiRequest._validate_response(r, OpenApiReqType.GET)
            if not res.result:
                res.ignore_result()
                return res.info
            return r.content.decode('utf8')

    @staticmethod
    def update_nvue_changeset(request_data) -> Tuple[bool, str]:
        result, err = True, ''
        if OpenApiRequest.changeset is None:
            res = OpenApiRequest.create_nvue_changest(request_data)
            result = res.result
            if not result:
                logging.info(f'Failed to create revision. Abort the current request\nInfo: {res.info}')
                OpenApiRequest.clear_changeset_and_payload()
                err = res.info
        return result, err

    @staticmethod
    def send_patch_request(request_data, op_params=''):
        with allure.step("Send PATCH request"):
            with allure.step("Add data to patch request"):
                OpenApiRequest.payload = {request_data.param_name: request_data.param_value} \
                    if request_data.param_value == 'null' else request_data.param_value
                if request_data.param_value == 'save':
                    OpenApiRequest.payload = {request_data.param_name: request_data.param_value}
                url = OpenApiRequest._get_endpoint_url(request_data) + request_data.resource_path

            res, err = OpenApiRequest.update_nvue_changeset(request_data)
            if not res:
                return err

            logging.info("Send PATCH request")
            r = requests.patch(url=url,
                               auth=OpenApiRequest._get_http_auth(request_data),
                               data=json.dumps(OpenApiRequest.payload).replace('"null"', "null"),
                               params={"rev": OpenApiRequest.changeset},
                               headers=REQ_HEADER, **OpenApiRequest._get_client_security_config())
            OpenApiRequest.print_request(r.request, request_data)
            OpenApiRequest.print_response(r, OpenApiReqType.PATCH)
            res = OpenApiRequest._validate_response(r, OpenApiReqType.PATCH)
            res.ignore_result()  # todo: maybe this function should return ResultObj instead of str?
            return res.info

    @staticmethod
    def send_delete_request(request_data, op_params=''):
        with allure.step('Send DELETE request'):
            if op_params:
                request_data.param_value = 'null'
                return OpenApiRequest.send_patch_request(request_data, op_params)
            else:
                res, err = OpenApiRequest.update_nvue_changeset(request_data)
                if not res:
                    return err

                if request_data.param_name == '':
                    url = OpenApiRequest._get_endpoint_url(request_data) + request_data.resource_path
                else:
                    url = OpenApiRequest._get_endpoint_url(request_data) + request_data.resource_path + "/" + \
                        request_data.param_name

                logging.info("Send DELETE request")
                r = requests.delete(url=url,
                                    auth=OpenApiRequest._get_http_auth(request_data),
                                    params={"rev": OpenApiRequest.changeset},
                                    headers=REQ_HEADER, **OpenApiRequest._get_client_security_config())

                OpenApiRequest.print_request(r.request, request_data)
                OpenApiRequest.print_response(r, OpenApiReqType.DELETE)
                res = OpenApiRequest._validate_response(r, OpenApiReqType.DELETE).ignore_result()
                return res.info

    @staticmethod
    def send_action_request(request_data, expected_str='') -> str:
        # todo: refactor this function to return a result-obj, or better yet: to raise exception in case of action fail
        with allure.step("Send POST request"):
            req_url = '{url}{resource_path}'.format(url=OpenApiRequest._get_endpoint_url(request_data),
                                                    resource_path=request_data.resource_path)

            OpenApiRequest.payload = {request_data.param_name: request_data.param_value}

            r = requests.post(url=req_url,
                              auth=OpenApiRequest._get_http_auth(request_data),
                              data=json.dumps(OpenApiRequest.payload),
                              headers=REQ_HEADER, **OpenApiRequest._get_client_security_config())
            OpenApiRequest.print_request(r.request, request_data)
            OpenApiRequest.print_response(r, OpenApiReqType.ACTION)

            validation_res = OpenApiRequest._check_action_post_response(r)
            validation_res.ignore_result()
            if not validation_res.result:
                returned_value = f"{OpenApiCommandHelper.ACTION_ERROR} {validation_res.info}"
                logger.info(returned_value)
                return returned_value

            r = r.json()
            response = json.dumps(r, indent=2)
            if not response.isnumeric():
                assert isinstance(r, dict) and r.get('status') != 200 and 'title' in r and 'detail' in r, \
                    f"In case of bad request expect status!=200 and some error message, but response is: {r}"
                returned_value = f"{OpenApiCommandHelper.ACTION_ERROR} {r['title']}: {r['detail']}"
                logger.info(returned_value)
                return returned_value
        response_for_get_request = OpenApiRequest._send_get_req_and_wait_till_completed(
            request_data, response, expected_str)
        return response_for_get_request

    @staticmethod
    def _send_get_req_and_wait_till_completed(request_data, rev, expected_str='') -> str:
        with allure.step("Send GET request"):
            req_url = OpenApiRequest._get_endpoint_url(request_data) + "/action/" + rev
            auth = OpenApiRequest._get_http_auth(request_data)

            while True:
                r = requests.get(url=req_url, auth=auth, timeout=30, **OpenApiRequest._get_client_security_config())
                # Note: this 30-second timeout is for obtaining the action-status, *not* for completing the action.
                # This tool does not define a timeout for completing the action since there's a great variance in
                # completion times for different actions, for example CPLD update takes ~15 minutes.
                OpenApiRequest.print_request(r.request, request_data)
                OpenApiRequest.print_response(r, OpenApiReqType.GET)
                response = json.loads(r.content.decode('utf-8'))
                action_state = response['state']
                action_status = response['status']
                if expected_str:
                    try:
                        ValidationTool.verify_any_string_in_string(action_status, expected_str).verify_result()
                        logger.info(f'Action finished - found expected string: {action_status}')
                        return action_status
                    except AssertionError:
                        pass

                if action_state == "action_success":
                    logger.info('Action finished - state action_success')
                    return action_status
                elif action_state not in ("", "running", "start"):
                    logger.info(f'Action finished - state {action_state}')
                    issue = ''
                    try:
                        issue = response['issue']
                        issue = issue[0]['message']
                    except Exception:
                        pass
                    if action_state == OpenApiCommandHelper.ACTION_ERROR:
                        return f'{OpenApiCommandHelper.ACTION_ERROR}: {str(issue)}'
                    else:
                        raise Exception(action_status + " - issue: " + str(issue))

                time.sleep(2)


class OpenApiCommandHelper:
    ACTION_ERROR = 'action_error'
    req_method = {OpenApiReqType.GET: OpenApiRequest.send_get_request,
                  OpenApiReqType.PATCH: OpenApiRequest.send_patch_request,
                  OpenApiReqType.DELETE: OpenApiRequest.send_delete_request,
                  OpenApiReqType.ACTION: OpenApiRequest.send_action_request,
                  OpenApiReqType.APPLY: OpenApiRequest.apply_nvue_changeset}

    @staticmethod
    def update_open_api_port(port_num):
        OpenApiRequest.port_num = port_num
        logging.info(f"OpenApi port number updated to {port_num}")

    @staticmethod
    def execute_script(user_name, password, req_type, dut_ip, resource_path, op_param_name='', op_param_value='', client_certs_after_apply: CertInfo = None):
        request_data = RequestData(user_name, password, dut_ip, resource_path, op_param_name, op_param_value)
        if req_type == OpenApiReqType.APPLY:
            return OpenApiRequest.apply_nvue_changeset(request_data, op_param_name, client_certs_after_apply=client_certs_after_apply)
        else:
            return OpenApiCommandHelper.req_method[req_type](request_data, op_param_name)

    @staticmethod
    def execute_action(action_type, user_name, password, dut_ip, resource_path, params, expected_str=''):
        request_data = RequestData(user_name, password, dut_ip, resource_path.strip(), action_type, params)
        return OpenApiCommandHelper.req_method[OpenApiReqType.ACTION](request_data, expected_str)
