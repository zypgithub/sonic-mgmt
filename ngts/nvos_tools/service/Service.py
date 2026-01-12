import logging
import os
import time
from typing import Tuple, Union, Dict

import pytest
from retry import retry

from ngts.cli_wrappers.nvue.nvue_system_clis import NvueSystemCli
from ngts.cli_wrappers.openapi.openapi_system_clis import OpenApiSystemCli
from ngts.constants.constants import InfraConst
from ngts.helpers.sanitizer_helper import check_sanitizer_and_store_dump
from ngts.nvos_constants.constants_nvos import ApiType, ServiceConsts
from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.service.Control import Control
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class Service(BaseComponent):
    def __init__(self, parent_obj=None, devices_dut=None, force_api=None):
        assert force_api in ApiType.ALL_TYPES + [None], f'Argument "force_api" must be in {ApiType.ALL_TYPES + [None]}. Given: {force_api}'
        BaseComponent.__init__(self, parent=parent_obj,
                               api={ApiType.NVUE: NvueSystemCli, ApiType.OPENAPI: OpenApiSystemCli}, path='/service', force_api=force_api)
        self.control = Control(self)
