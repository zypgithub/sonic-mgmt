import logging

import allure
from retry import retry

from ngts.cli_wrappers.nvue.nvue_ib_interface_clis import NvueIbInterfaceCli
from ngts.cli_wrappers.openapi.openapi_ib_interface_clis import OpenApiIbInterfaceCli
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.nvos_tools.acl.acl import Acl
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts, NvosConsts
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool

logger = logging.getLogger()


class PortRequirements:
    default_port_requirements = {IbInterfaceConsts.NAME: "",
                                 IbInterfaceConsts.DESCRIPTION: "",
                                 IbInterfaceConsts.LINK_MTU: "",
                                 IbInterfaceConsts.LINK_BREAKOUT: "",
                                 IbInterfaceConsts.LINK_SPEED: "",
                                 IbInterfaceConsts.LINK_IB_SPEED: "",
                                 IbInterfaceConsts.LINK_STATE: "",
                                 IbInterfaceConsts.LINK_LOGICAL_PORT_STATE: "",
                                 IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE: "",
                                 IbInterfaceConsts.TYPE: ""}
    port_requirements = None
    interface_type = ''

    def __init__(self, interface_type=''):
        self.port_requirements = self.default_port_requirements.copy()
        self.interface_type = interface_type  # Port type refers to "internal/external/fnm ports"

    def __str__(self):
        return self.__class__.__name__ + "=" + str({k: v for k, v in self.port_requirements.items() if v})

    def set_port_name(self, name):
        self.port_requirements[IbInterfaceConsts.NAME] = name

    def set_port_description(self, description):
        self.port_requirements[IbInterfaceConsts.DESCRIPTION] = description

    def set_port_speed(self, speed):
        self.port_requirements[IbInterfaceConsts.LINK_SPEED] = speed

    def set_port_ib_speed(self, ib_speed):
        self.port_requirements[IbInterfaceConsts.LINK_IB_SPEED] = ib_speed

    def set_port_state(self, state):
        self.port_requirements[IbInterfaceConsts.LINK_STATE] = state

    def set_port_type(self, req_type):
        self.port_requirements[IbInterfaceConsts.TYPE] = req_type

    def set_port_logical_state(self, req_type):
        self.port_requirements[IbInterfaceConsts.LINK_LOGICAL_PORT_STATE] = req_type


class Port(BaseComponent):
    api_obj = {ApiType.NVUE: NvueIbInterfaceCli, ApiType.OPENAPI: OpenApiIbInterfaceCli}

    def __init__(self, name='eth0', show_output_dictionary={}, name_in_redis='', parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj,
                               api={ApiType.NVUE: NvueIbInterfaceCli, ApiType.OPENAPI: OpenApiIbInterfaceCli}, path='')
        self.name = name
        self.show_output_dictionary = show_output_dictionary
        self.name_in_redis = name_in_redis
        self.interface = Interface(self, name)
        self.acl = Acl(self)

    def __str__(self):
        return f"{self.__class__.__name__}('{self.name}')"

    def __repr__(self):
        return str(self)

    @staticmethod
    def get_list_of_active_ports(port_type=IbInterfaceConsts.IB_PORT_TYPE, interface_type=''):
        """
        Return a list of ports which are connected to a traffic server
        """
        with allure.step('Get a list of ports which state is up and logical state is Active'):
            port_requirements_object = PortRequirements(interface_type)
            port_requirements_object.set_port_state(NvosConsts.LINK_STATE_UP)
            port_requirements_object.set_port_type(port_type)
            port_requirements_object.set_port_logical_state("Active")
            up_port_list = Port.get_list_of_ports(None, port_requirements_object)

        return up_port_list

    @staticmethod
    def get_list_of_ports(dut_engine=None, port_requirements_object=None):
        """
        Returns a list of port according to port_requirements
        :param dut_engine: ssh dut engine
        :param port_requirements_object: PortRequirements object
        :return: a list of Port objects
        """
        with allure.step('Search for ports that meet provided requirements'):
            if not dut_engine:
                dut_engine = TestToolkit.engines.dut

            logging.info("get_list_of_ports - Searching for relevant ports")
            output_dictionary = OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
                Port.show_interface(dut_engine)).verify_result()

            port_list = []

            if not port_requirements_object or not port_requirements_object.port_requirements:
                logging.info("get_list_of_ports - port_requirements not provided. Selecting all ports.")
                for port_name in output_dictionary.keys():
                    if port_requirements_object is not None:
                        if port_requirements_object.interface_type in port_name:
                            port_list.append(Port(port_name, "", ""))
                    else:
                        port_list.append(Port(port_name, "", ""))
                return port_list

            for port_name, port_details in output_dictionary.items():
                select_port = True
                if port_requirements_object.interface_type not in port_name:
                    select_port = False

                for field_name, port_requirements_list in port_requirements_object.port_requirements.items():

                    if field_name == IbInterfaceConsts.NAME and port_requirements_list and \
                       port_requirements_list != port_name:
                        select_port = False
                        break
                    elif field_name == IbInterfaceConsts.LINK_STATE and isinstance(port_requirements_list, list):
                        if not any(port_details[field_name] == expected_state for expected_state in port_requirements_list):
                            select_port = False
                            break
                    elif port_requirements_list and field_name in port_details.keys() and port_details[field_name] != port_requirements_list:
                        select_port = False
                        break

                if select_port:
                    port_list.append(Port(port_name, {}, ""))
                    logging.info("get_list_of_ports - {port_name} meets the requirements".format(port_name=port_name))

            return port_list

    def update_output_dictionary(self, dut_engine=None):
        """
        Execute "show" command and create the output dictionary for a specific port
        :param dut_engine: ssh engine
        """
        with allure.step('Execute "show" command and create the output dictionary for {port_name}'.format(
                port_name=self.name)):
            if not dut_engine:
                dut_engine = TestToolkit.engines.dut

            logging.info("Updating output dictionary of '{port_name}'".format(port_name=self.name))
            self.show_output_dictionary = OutputParsingTool.parse_show_interface_output_to_dictionary(
                Port.show_interface(dut_engine, self.name)).get_returned_value()

    @staticmethod
    def show_interface(dut_engine=None, port_names="", fae_param="", output_format=OutputFormat.json):
        """
        Executes show interface
        :param output_format: OutputFormat
        :param port_names: ports on which to run show command
        :param fae_param: optional - to command with fae
        :param dut_engine: ssh engine
        :return: str/json output
        """
        with allure.step('Execute show interface for {port_names}'.format(port_names=port_names)):
            if not dut_engine:
                dut_engine = TestToolkit.engines.dut

            logging.info("Executing show interface for {port_names}".format(port_names=port_names))
            return Port.api_obj[TestToolkit.tested_api].show_interface(engine=dut_engine,
                                                                       port_name=port_names,
                                                                       fae_param=fae_param,
                                                                       output_format=output_format)

    @staticmethod
    @retry(Exception, tries=15, delay=5)
    def wait_for_port_state(port_obj, expected_state):
        with allure.step("Waiting for port {} state {}".format(port_obj.name, expected_state)):
            output_dictionary = OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                port_obj.interface.link.show()).get_returned_value()
            current_state = output_dictionary[IbInterfaceConsts.LINK_STATE]
            assert current_state == expected_state, "Current state {} is not {} as expected".format(current_state,
                                                                                                    expected_state)

    def get_port_ip_addresses(self, dut_engine):
        with allure.step(f"Get mgmt port {self.name} ip addresses"):
            ip_addresses_show = list(OutputParsingTool.parse_json_str_to_dictionary(
                self.interface.ip.address.show(dut_engine=dut_engine)).get_returned_value())
        return ip_addresses_show[0].split("/")[0]

    def update_port_name(self, name):
        self.name = name
        self.interface = Interface(self, name)
