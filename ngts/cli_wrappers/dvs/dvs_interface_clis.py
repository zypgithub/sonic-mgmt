import logging
import json
import os
import re
import time
import allure
import netmiko

from ngts.cli_wrappers.interfaces.interface_general_clis import GeneralCliInterface

logger = logging.getLogger()


class DvsInterfaceCli(GeneralCliInterface):

    def __init__(self, engine, dut_alias):
        self.engine = engine
        self.dut_alias = dut_alias

    def clear_counters(self):
        pass
