from typing import Union

from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System


def verify_api_compression_state(system: System, expected_compression: Union[str, None]) -> None:
    applied_compression: Union[str, None] = OutputParsingTool.parse_json_str_to_dictionary(system.api.show()).get_returned_value()[SystemConsts.ApiConsts.COMPRESSION]
    assert applied_compression == expected_compression, \
        f"Compression {'shown' if applied_compression else 'not shown'}, but show is {'expected' if expected_compression else 'not expected'}"
