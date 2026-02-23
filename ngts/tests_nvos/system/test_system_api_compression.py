import gzip
import json
import random
import subprocess
import tempfile
from infra.tools.linux_tools.linux_tools import LinuxSshEngine
import pytest
from typing import Callable, Dict, Any, Union

from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.CurlCmdBuilder import CurlCmdBuilder
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.ngts_types import EnginesT
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.system.helpers import verify_api_compression_state

ACCEPTED_ENCODING_GZIP: Dict[str, str] = {'Accept-Encoding': 'gzip'}
REQUEST_TIMEOUT: float = 30.0  # [sec] - OpenAPI request timeout


class ExpectedFileData:
    JSON: str = 'JSON text data'
    GZIP: str = 'gzip compressed data'


def _curl_wrapper(
    dut_engine: LinuxSshEngine,
    method: str,
    resource: BaseComponent,
    headers: Dict[str, str] = {},
    output_body_file_path: str = None,
    output_headers_file_path: str = None
) -> str:
    """Execute curl command with specified parameters and return response."""
    cmd: CurlCmdBuilder = CurlCmdBuilder(method=method, host=dut_engine.ip, resource=resource.get_resource_path())
    cmd = cmd.user_creds(dut_engine.username, dut_engine.password)
    cmd = cmd.insecure()
    if headers:
        for header_name, header_value in headers.items():
            cmd = cmd.header(header_name, header_value)
    if output_body_file_path:
        cmd = cmd.output_file(output_body_file_path)
    if output_headers_file_path:
        cmd = cmd.dump_header(output_headers_file_path)
    p = subprocess.Popen(cmd.build(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    try:
        stdout, stderr = p.communicate(timeout=REQUEST_TIMEOUT)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()  # cleanup zombie process
        pytest.fail(f"Curl request exceeded timeout of {REQUEST_TIMEOUT}s")
    assert p.returncode == 0, f"Curl return code value is {p.returncode} - expected 0. Details: {stderr.decode('utf-8')}"
    return stdout.decode('utf-8')


def _get_file_type(file_path: str) -> str:
    """Get file type from file path by checking magic bytes and content."""
    with open(file_path, 'rb') as f:
        data = f.read()

    # Check for gzip magic bytes: 0x1f 0x8b are the first two bytes of any gzip file
    # See RFC 1952 (GZIP file format specification) section 2.3.1
    if len(data) >= 2 and data[0] == 0x1f and data[1] == 0x8b:
        return ExpectedFileData.GZIP

    # Try to decode as JSON
    try:
        data.decode('utf-8')
        # Additional check: try to parse as JSON to be more confident
        json.loads(data.decode('utf-8'))
        return ExpectedFileData.JSON
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass

    return 'unknown data'


@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_system_api_compression(engines: EnginesT, test_api: ApiType):
    """
    Test API compression functionality with gzip encoding.
    Test Steps:
        1. Set compression to gzip and apply configuration
        2. Verify compression setting is applied correctly
        3. Send API request with Accept-Encoding: gzip header
        4. Verify response contains Content-Encoding: gzip header
        5. Verify response body is gzip compressed data
        6. Compare NVUE API response with OpenAPI response for consistency
        7. Unset compression and verify it's removed
    """
    system = System()
    try:
        with allure.step(f'Set compression to {SystemConsts.ApiConsts.CompressionT.GZIP} and apply config'):
            TestToolkit.tested_api = test_api
            system.api.set(op_param_name=SystemConsts.ApiConsts.COMPRESSION, op_param_value=SystemConsts.ApiConsts.CompressionT.GZIP, apply=True).verify_result()
            verify_api_compression_state(system, SystemConsts.ApiConsts.CompressionT.GZIP)
        with allure.step('Request API with compression'):
            interface = Interface(None)
            with tempfile.NamedTemporaryFile(prefix='response_headers_') as tmp_header_f:
                with tempfile.NamedTemporaryFile(prefix='response_body_') as tmp_body_f:
                    _curl_wrapper(engines.dut, 'GET', interface, headers=ACCEPTED_ENCODING_GZIP, output_body_file_path=tmp_body_f.name, output_headers_file_path=tmp_header_f.name)
                    res_headers = tmp_header_f.read().decode('utf-8')
                    assert f'Content-Encoding: {SystemConsts.ApiConsts.CompressionT.GZIP}' in res_headers, "Content-Encoding value is absent - expected gzip"
                    file_type = _get_file_type(tmp_body_f.name)
                    assert ExpectedFileData.GZIP in file_type, f"File type value is {file_type.strip()} - expected {ExpectedFileData.GZIP}"
        with allure.step('Compare NVUE API response with OpenAPI API response'):
            TestToolkit.tested_api = ApiType.NVUE
            nvue_output: Dict[str, Any] = OutputParsingTool.parse_json_str_to_dictionary(system.version.show()).get_returned_value()
            TestToolkit.tested_api = ApiType.OPENAPI
            openapi_output: Dict[str, Any] = OutputParsingTool.parse_json_str_to_dictionary(system.version.show()).get_returned_value()
            ValidationTool.compare_dictionaries(nvue_output, openapi_output).verify_result()
    finally:
        with allure.step("Verify Compression unset"):
            TestToolkit.tested_api = test_api
            system.api.unset(op_param=SystemConsts.ApiConsts.COMPRESSION, apply=True).verify_result()
            verify_api_compression_state(system, None)


@pytest.mark.parametrize('compression_set_cmd, gzip_header, is_compression_set', [
    pytest.param(
        lambda: System().api.set(op_param_name=SystemConsts.ApiConsts.COMPRESSION, op_param_value=SystemConsts.ApiConsts.CompressionT.GZIP, apply=True).verify_result(),
        {},
        True,
        id='compress-enabled-gzip-not-requested'
    ),
    pytest.param(
        lambda: System().api.unset(op_param=SystemConsts.ApiConsts.COMPRESSION, apply=True).verify_result(),
        ACCEPTED_ENCODING_GZIP,
        False,
        id='compress-disabled-gzip-requested'
    )
])
def test_system_api_compress_bad_flow(engines: EnginesT, register_cleanup, compression_set_cmd: Callable, gzip_header: Dict[str, str], is_compression_set: bool):
    """
    Test API compression behavior in negative scenarios.
    Verifies that compression is not applied when:
        1. Compression is enabled but client doesn't request gzip encoding
        2. Compression is disabled but client requests gzip encoding
    Test Steps:
        1. Configure API compression based on test parameter
        2. Verify compression configuration matches expected state
        3. Send API request with specified headers
        4. Verify response body is plain JSON (not compressed)
    """
    TestToolkit.tested_api = random.choice(ApiType.ALL_TYPES)
    system = System()
    if not is_compression_set:
        register_cleanup(lambda: system.api.unset(op_param=SystemConsts.ApiConsts.COMPRESSION, apply=True).verify_result())
    with allure.step('Set compression'):
        compression_set_cmd()
    with allure.step('Verify compression is set to expected value'):
        output_compression: Union[str, None] = OutputParsingTool.parse_json_str_to_dictionary(system.api.show()).get_returned_value()[SystemConsts.ApiConsts.COMPRESSION]
        assert (output_compression == SystemConsts.ApiConsts.CompressionT.GZIP) == is_compression_set, f"Compression is {output_compression} - expected {is_compression_set}"
    with allure.step('Request API with compression'):
        with tempfile.NamedTemporaryFile(prefix='response_body_') as tmp_body_f:
            with tempfile.NamedTemporaryFile(prefix='response_headers_') as tmp_header_f:
                _curl_wrapper(engines.dut, 'GET', system.version, headers=gzip_header, output_body_file_path=tmp_body_f.name, output_headers_file_path=tmp_header_f.name)
                res_headers = tmp_header_f.read().decode('utf-8')
                assert f'Content-Encoding: {SystemConsts.ApiConsts.CompressionT.GZIP}' not in res_headers, "Content-Encoding value is gzip - expected absent"
                file_type = _get_file_type(tmp_body_f.name)
                assert ExpectedFileData.JSON in file_type, f"File type value is {file_type.strip()} - expected {ExpectedFileData.JSON}"
