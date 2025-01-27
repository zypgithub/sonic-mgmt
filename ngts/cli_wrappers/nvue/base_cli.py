from abc import abstractmethod, ABCMeta
from typing import Optional, Tuple, Union, Iterable

from ngts.nvos_tools.infra.DutUtilsTool import RebootParams
from ngts.nvos_tools.infra.ResultObj import ResultObj


class BaseCli(metaclass=ABCMeta):
    """Abstract base-class for both NvueBaseCli and OpenApiBaseCli"""
    sub_strings_to_search = ['ib', 'sm', 'quantum']
    check_output_strings = False
    cli_name = ""

    @staticmethod
    @abstractmethod
    def show(engine, resource_path, op_param, output_format): pass

    @staticmethod
    @abstractmethod
    def set(engine, resource_path, op_param_name, op_param_value): pass

    @staticmethod
    @abstractmethod
    def unset(engine, resource_path, op_param): pass

    @staticmethod
    @abstractmethod
    def action_deprecated(engine, device, action_type, resource_path, suffix, param_name, param_value, output_format,
                          expect_reboot, recovery_engine, topology_obj, should_succeed, system_is_ready_timeout,
                          track_boot_intervals, deny_reboot, press_y, expected_output: str): pass

    @classmethod
    @abstractmethod
    def action(cls, action_str: str, resource_path: str, main_param: Tuple[str, Union[str, int]],
               flags: Union[str, Iterable[str]], params: dict, engine, reboot_params: Optional[RebootParams],
               send_user_confirmation: Optional[str], expected_output: str, device) -> ResultObj: pass
