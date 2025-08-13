#!/usr/bin/env python
import allure
import json
import logging
import os
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.scripts.code_coverage.code_coverage_consts import SharedConsts

logger = logging.getLogger()


def get_dest_path(engine, coverage_path):
    """
    Creates a destination path for coverage reports based on the NVOS version.

    Args:
        engine: The engine object to get system information from
        coverage_path: Base coverage path

    Returns:
        str: The destination path for coverage reports
    """
    with allure.step("Get nvos version"):
        output = json.loads(engine.run_cmd("nv show system version -o json"))
        nvos_version = output["version"]
        release = TestToolkit.version_to_release(nvos_version)
        nvos_version = nvos_version.replace("nvos-", "")

    dest = f"{coverage_path}/{release}_{nvos_version}"

    with allure.step("Create coverage folder if not exists"):
        if not os.path.exists(dest):
            os.makedirs(dest)
            os.chmod(dest, 0o777)
            sub_dir = dest + SharedConsts.C_DIR
            os.makedirs(sub_dir)
            os.chmod(sub_dir, 0o777)
            sub_dir = dest + SharedConsts.PYTHON_DIR
            os.makedirs(sub_dir)
            os.chmod(sub_dir, 0o777)

    return dest


def _get_coverage_path_from_target_version(target_version):
    """
    Transforms a target version path into a coverage path.

    Args:
        target_version: Path to the target version

    Returns:
        str: The coverage path

    Example:
        Input: /auto/sw_system_release/nos/nvos/25.02.4934-024/amd64/dev/nvos-amd64-25.02.4934-024.bin
        Output: /auto/sw_system_release/nos/nvos/25.02.4934-024/amd64/dev/coverage
    """
    path_parts = target_version.split('/')
    path_parts.pop()
    coverage_path = '/'.join(path_parts) + '/coverage'
    return coverage_path
