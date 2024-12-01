import logging
import time


from abc import ABC, abstractmethod
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import BiosConsts

logger = logging.getLogger()


class BiosTool(ABC):
    """
    Abstract Base Class for BIOS tools.
    """

    def __init__(self, topology_obj, dut_engine, nvue_cli_obj, dut_ip):
        self.topology_obj = topology_obj
        self.dut_engine = dut_engine
        self.nvue_cli_obj = nvue_cli_obj
        self.dut_ip = dut_ip

    @property
    @abstractmethod
    def BIOS_MENU_PAGES(self):
        """
        Abstract property to be defined in subclasses.
        Each subclass provides its own list of supported features.
        """
        pass

    @property
    @abstractmethod
    def CREATE_NEW_PASSWORD(self):
        """Abstract property to create a new password."""
        pass

    @property
    @abstractmethod
    def ENTER_CURRENT_PASSWORD(self):
        """Abstract property to enter the current password."""
        pass

    @property
    @abstractmethod
    def CLEAR_OLD_PASSWORD(self):
        """Abstract property to clear the old password."""
        pass

    def config_flow(self):
        with allure.step('Entering BIOS on: {}'.format(self.dut_ip)):
            self.enter_bios(self.topology_obj, self.nvue_cli_obj)

        serial_engine = self.nvue_cli_obj.enter_serial_connection_context(self.topology_obj)
        with allure.step('Configuring empty BIOS password'):
            self.go_to_bios_page(serial_engine, "Main", "Security", self.BIOS_MENU_PAGES)
            self.bios_find_and_select(serial_engine, "Administrator Password")
            self.disable_bios_password(serial_engine)

        with allure.step('Enabling network stack configuration'):
            self.go_to_bios_page(serial_engine, "Security", "Advanced", self.BIOS_MENU_PAGES)
            self.bios_find_and_select(serial_engine, "Network Stack Configuration")
            self.enable_network_stack(serial_engine)

        with allure.step('Done configuring network stack and BIOS password, Save and exit the BIOS'):
            self.go_to_bios_page(serial_engine, "Advanced", "Save & Exit", self.BIOS_MENU_PAGES)
            self.bios_find_and_select(serial_engine, "Save Changes and Exit")
            serial_engine.run_cmd(BiosConsts.ENTER, '.*', timeout=3, send_without_enter=True)

        logger.info("BIOS configuration script finished running, will now wait for machine to come up")

    def enter_bios(self, topology_obj, nvue_cli_obj):
        '''
        @summary: this method will remote reboot the given switch and enter the BIOS menu
        @param topology_obj: topology object
        @param nvue_cli_obj: NvueGeneralCli object
        '''

        logger.info("Initializing serial connection to device")
        serial_engine = nvue_cli_obj.enter_serial_connection_context(topology_obj)
        logger.info('Executing remote reboot')
        nvue_cli_obj.remote_reboot(topology_obj, wait_till_alive=False)
        logger.info("Waiting for enter BIOS prompt")
        serial_engine.run_cmd('', [BiosConsts.BIOS_START_REGEX], timeout=240, send_without_enter=True)

        time.sleep(BiosConsts.KEY_STROKE_SLEEP)
        _, respond = serial_engine.run_cmd(BiosConsts.CTRL_B,
                                           [BiosConsts.BIOS_PASSWORD_PROMPT, BiosConsts.BIOS_HOMEPAGE_TITLE],
                                           timeout=240,
                                           send_without_enter=True)
        time.sleep(BiosConsts.KEY_STROKE_SLEEP)
        if respond == 1:
            logger.info('Entered Bios Menu, no password was needed')
        else:
            logger.info('Detected Password prompt, sending {}'.format(BiosConsts.DEFAULT_BIOS_PASSWORD))
            serial_engine.run_cmd(BiosConsts.DEFAULT_BIOS_PASSWORD, '.*', timeout=10, send_without_enter=True)
            time.sleep(BiosConsts.KEY_STROKE_SLEEP)
            _, respond = serial_engine.run_cmd(BiosConsts.ENTER,
                                               [BiosConsts.INVALID_PASSWORD_PROMPT, BiosConsts.BIOS_HOMEPAGE_TITLE],
                                               timeout=10, send_without_enter=True)

            if respond == 0:
                raise Exception("Could not enter the BIOS using the known default password")
            else:
                logger.info('Entered BIOS Menu using default BIOS password')

    def change_bios_page(self, serial_engine, direction_key, expected_header):
        '''
        @summary: This method change one BIOS page in a specific direction
        @param serial_engine: The RCON serial connection to the switch
        @param direction_key: The direction we want to change the page - BiosConsts.LEFT_ARROW or BiosConsts.RIGHT_ARROW
        @param expected_header: The header we expect to see in the next page
        '''
        time.sleep(BiosConsts.KEY_STROKE_SLEEP)
        logger.info("Pressing {}, expecting to be in {} page".format(
            "left arrow key" if direction_key == BiosConsts.LEFT_ARROW else "right arrow key", expected_header))
        serial_engine.run_cmd(direction_key, BiosConsts.SELECTED_PAGE_REGEX.format(expected_header), timeout=10,
                              send_without_enter=True)
        logger.info("successfully moved to {} page".format(expected_header))

    def go_to_bios_page(self, serial_engine, current_page, target_page, setting_pages):
        '''
        @summary: This method changes pages in the BIOS settings
        @param serial_engine: The RCON serial connection to the switch
        @param current_page: The current BIOS setting page we are in
        @param target_page: The BIOS setting page we want to go to
        @param setting_pages: The list of the BIOS setting pages relevant for this CPU
        '''
        assert target_page in setting_pages, BiosConsts.MISSING_PAGE_ERR.format(target_page, setting_pages)
        # rotate the list to start at current page
        # e.g. if the header list is ["Main", "Home", "Boot", "Exit"] and current_page is "Home" we will get
        # ["Home", "Boot", "Exit", "Main"]
        setting_pages = setting_pages[setting_pages.index(current_page):] + setting_pages[
            :setting_pages.index(current_page)]
        # zip the header list with itself shifted by one to create (curr, next) tuples
        # e.g. for the list above: [("Home", "Boot"), ("Boot", "Exit"), ("Exit", "Main"), ("Main", "Home")]
        for curr_p, target_p in zip(setting_pages, setting_pages[1:] + setting_pages[:1]):
            logger.info("Changing page from {} to {}".format(curr_p, target_p))
            self.change_bios_page(serial_engine, direction_key=BiosConsts.RIGHT_ARROW, expected_header=target_p)
            if target_p == target_page:
                logger.info("Reached target page '{}'".format(target_page))
                break

    def bios_find_and_select(self, serial_engine, title_name, max_selections=BiosConsts.MAX_SELECTIONS_PER_PAGE):
        '''
        @summary: This method find a specific entry (and selects it - aka press Enter) on a BIOS setting page
        @param serial_engine: The RCON serial connection to the switch
        @param title_name: The entry we would like to select on the page
        @param max_selections: Integer, the number of attempts to scroll down the menu until we declare failure
        '''
        logger.info("Searching for selection: {}".format(title_name))
        for iteration in range(max_selections):
            try:
                serial_engine.serial_engine.expect('.*')
                time.sleep(BiosConsts.KEY_STROKE_SLEEP)
                logger.info('Pressing DOWN arrow')
                serial_engine.serial_engine.send(BiosConsts.DOWN_ARROW)
                time.sleep(BiosConsts.KEY_STROKE_SLEEP)
                serial_engine.serial_engine.expect("\\x1b[[]1;37;47m.*{}".format(title_name),
                                                   timeout=BiosConsts.PEXPECT_TIMEOUT)
                break
            except Exception:
                logger.info('Expected option was not found on last key stroke')
        else:
            raise Exception("Could not find the title {} after {} down key presses".format(title_name, max_selections))

        logger.info("found title {}, pressing the Enter key".format(title_name))
        serial_engine.run_cmd(BiosConsts.ENTER, '.*', timeout=BiosConsts.PEXPECT_TIMEOUT, send_without_enter=True)

    def bios_go_back(self, serial_engine):
        '''
        @summary: This method will just press ESC once
        @param serial_engine: The RCON serial connection to the switch
        '''
        serial_engine.run_cmd(BiosConsts.ESC, '.*', timeout=BiosConsts.PEXPECT_TIMEOUT, send_without_enter=True)

    def disable_bios_password(self, serial_engine):
        '''
        @summary: This method will disable the BIOS password, it assumes we used bios_find_and_select
                to find the "administration password" field and click it
        @param serial_engine: The RCON serial connection to the switch
        '''
        logger.info("Changing BIOS password if there's one")
        _, respond = serial_engine.run_cmd('', [self.CREATE_NEW_PASSWORD, self.ENTER_CURRENT_PASSWORD],
                                           timeout=BiosConsts.PEXPECT_TIMEOUT,
                                           send_without_enter=True)
        time.sleep(BiosConsts.KEY_STROKE_SLEEP)

        if respond == 0:
            logger.info('No password is configured, returning to main Security Page')
            self.bios_go_back(serial_engine)
        else:
            logger.info("Entering {} as current password".format(BiosConsts.DEFAULT_BIOS_PASSWORD))
            for char in BiosConsts.DEFAULT_BIOS_PASSWORD:
                serial_engine.run_cmd(char, '.*', timeout=BiosConsts.PEXPECT_TIMEOUT, send_without_enter=True)
                time.sleep(BiosConsts.KEY_STROKE_SLEEP)

            serial_engine.run_cmd(BiosConsts.ENTER, self.CREATE_NEW_PASSWORD, timeout=BiosConsts.PEXPECT_TIMEOUT,
                                  send_without_enter=True)
            time.sleep(BiosConsts.KEY_STROKE_SLEEP)
            serial_engine.run_cmd(BiosConsts.ENTER, self.CLEAR_OLD_PASSWORD, timeout=BiosConsts.PEXPECT_TIMEOUT,
                                  send_without_enter=True)
            time.sleep(BiosConsts.KEY_STROKE_SLEEP)
            serial_engine.run_cmd(BiosConsts.ENTER, '.*', timeout=BiosConsts.PEXPECT_TIMEOUT, send_without_enter=True)

        logger.info("Finished setting empty BIOS password")

    def enable_network_stack(self, serial_engine):
        '''
        @summary: This method will enable the network stack in BIOS, it assumes we used bios_find_and_select
                to find the "Advanced -> Network Stack Configuration" field and click it
        @param serial_engine: The RCON serial connection to the switch
        '''
        logger.info("Enabling network stack if it was disabled")
        serial_engine.serial_engine.expect('.*')
        output, _ = serial_engine.run_cmd(BiosConsts.ENTER, BiosConsts.SELECTED_OPTION_LINE_REGEX, timeout=3,
                                          send_without_enter=True)
        time.sleep(BiosConsts.KEY_STROKE_SLEEP)

        if BiosConsts.ENABLED_SELECTED in output:
            logger.info('Network stack is already Enabled, no need to do anything')
            self.bios_go_back(serial_engine)
            time.sleep(BiosConsts.KEY_STROKE_SLEEP)
            self.bios_go_back(serial_engine)
        elif BiosConsts.DISABLED_SELECTED in output:
            logger.info("Network stack is Disabled, the script will now enable it")
            serial_engine.run_cmd(BiosConsts.DOWN_ARROW, ".", timeout=BiosConsts.PEXPECT_TIMEOUT,
                                  send_without_enter=True)
            time.sleep(BiosConsts.KEY_STROKE_SLEEP)
            serial_engine.run_cmd(BiosConsts.ENTER, ".", timeout=BiosConsts.PEXPECT_TIMEOUT, send_without_enter=True)
            time.sleep(BiosConsts.KEY_STROKE_SLEEP)
            self.bios_go_back(serial_engine)
            logger.info("Finished enabling Network stack")
        else:
            raise Exception(
                f"The script couldn't figure if the network stack is enabled or disabled \nOutput: {output}")
