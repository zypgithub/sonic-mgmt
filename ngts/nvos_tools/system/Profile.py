import allure
from ngts.nvos_constants.constants_nvos import ActionConsts, ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DutUtilsTool import RebootParams
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

CORE_CLOCK_KEY = 'core-clock'


class Profile(BaseComponent):
    PROFILE_CHANGE_RESPONSE_MESSAGES = ['System will be rebooted', 'Action succeeded',
                                        'Disconnecting from NVOS, system is offline during reboot']

    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/profile')

    def action_profile_change(self, params_dict=None, engine=None, device=None,
                              reboot_params=True, send_user_confirmation='y',
                              expected_output=None):
        """
        Execute 'nv action change system profile' with the given parameters.
        This action causes a system reboot.

        :param params_dict: Dictionary of profile parameters to change, e.g.
                           {'adaptive-routing-groups': 256} or {'adaptive-routing': 'enabled'}
        :param engine: LinuxSshEngine. If None, the DUT engine is used.
        :param device: BaseDevice. If None, the DUT is used.
        :param reboot_params: RebootParams object or True (default) since profile change causes reboot.
        :param send_user_confirmation: Confirmation response ('y' by default) for the reboot prompt.
        :param expected_output: Expected output string(s). Defaults to PROFILE_CHANGE_RESPONSE_MESSAGES.
        :return: ResultObj
        """
        params_dict = params_dict or {}
        expected_output = expected_output or self.PROFILE_CHANGE_RESPONSE_MESSAGES

        with allure.step(f'Execute action change for {self.get_resource_path()} with params {params_dict}'):
            engine = engine or TestToolkit.get_engine()
            device = device or TestToolkit.get_device()

            marker = TestToolkit.get_loganalyzer_marker(engine)

            result = self.action(
                action_str=ActionConsts.CHANGE,
                additional_params=params_dict,
                engine=engine,
                device=device,
                reboot_params=reboot_params,
                send_user_confirmation=send_user_confirmation,
                expected_output=expected_output
            )

            TestToolkit.add_loganalyzer_marker(engine, marker)

            return result

    def action_change_core_clock(
        self,
        core_clock_mhz,
        test_api,
        engine=None,
        flags=None,
        send_user_confirmation=None,
        reboot_params=True,
    ):
        """
        Execute nv action change fae system profile core-clock.
        """
        expected_output = self.PROFILE_CHANGE_RESPONSE_MESSAGES if test_api == ApiType.NVUE else ""

        engine = engine or TestToolkit.get_engine()

        with allure.step(f"Change FAE system profile core-clock to {core_clock_mhz}"):
            marker = TestToolkit.get_loganalyzer_marker(engine)

            action_kwargs = {
                "action_str": ActionConsts.CHANGE,
                "additional_params": {CORE_CLOCK_KEY: core_clock_mhz},
                "engine": engine,
                "reboot_params": reboot_params,
                "expected_output": expected_output,
            }
            if flags is not None:
                action_kwargs["flags"] = flags
            if send_user_confirmation is not None:
                action_kwargs["send_user_confirmation"] = send_user_confirmation

            result = self.action(**action_kwargs)

            TestToolkit.add_loganalyzer_marker(engine, marker)

            return result
