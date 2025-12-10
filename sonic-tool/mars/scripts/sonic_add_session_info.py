"""
@copyright:
    Copyright (C) Mellanox Technologies Ltd. 2001-2017.  ALL RIGHTS RESERVED.

    This software product is a proprietary product of Mellanox Technologies
    Ltd. (the "Company") and all right, title, and interest in and to the
    software product, including all associated intellectual property rights,
    are and shall remain exclusively with the Company.

    This software product is governed by the End User License Agreement
    provided with the software product.

@date:
    Nov 6, 2019

@author:
    xinw@mellanox.com

@changed:
    on June 4, 2023 by slutati@nvidia.com

@Location:
   /.autodirect/sw_regression/system/SONIC/MARS/bin/cmds/sonic_add_session_info.py

"""
#######################################################################
# Global imports
#######################################################################
import os
import re
import ast
#######################################################################
# Local imports
#######################################################################
from mars_open_community.additional_info.session_add_info import SessionAddInfo
from topology.TopologyAPI import TopologyAPI
from mlxlib.remote.mlxrpc import RemoteRPC
from mlxlib.common import trace

logger = trace.set_logger()

SONIC_SESSION_FACTS_PREFIX = "sonic_session_facts:"
DEFAULT_RPC_PORT = 18812


class SonicAddSessionInfo(SessionAddInfo):
    """
    Class to collect session info.
    Contains the conf_obj, extra_info dict if exist and session_info from the
    cmd if exists
    """

    def __init__(self, conf_obj, extra_info=None, session_info=None):
        """
        Constructor
        @param conf_obj:
            The configuration object, can get all the conf information from it.
        @param extra_info:
            Extra info dict from setup conf
        @param session_info:
            Info from the cmd info
        """
        SessionAddInfo.__init__(self, conf_obj, extra_info, session_info)

    def _parse_dict_string_from_output(self, output):
        """
        The function parses the result from the stdout output of the script
        ngts/scripts/sonic_add_session_info/test_sonic_add_session_info.py
        @param output:
            The output of the script test_sonic_add_session_info.py
        @return:
            A tuple (rc, output) - rc is 0 if the parsing was successful and 1 otherwise. The output is a dictionary
            with the information collected from test_sonic_add_session_info (empty dictionary if failed)
            i.e. {'version': 'SONiC.bluefield.215-4d25a6679_Internal', 'platform': 'arm64-nvda_bf-9009d3b600cvaa',
            'hwsku': 'Nvidia-9009d3b600CVAA-C1', 'asic': 'nvidia-bluefield', 'topology': 'dpu-1',
            'chip_type': 'BF3', 'sonic_branch': 'master'}"
        """
        pattern = r'{}(.*)'.format(SONIC_SESSION_FACTS_PREFIX)
        match = re.search(pattern, output)
        if match:
            dict_string = match.group(1).strip()
            rc = 0
            output = ast.literal_eval(dict_string)  # For MARS API, the value should return as a dictionary
            print("output={0}".format(str(output)))
        else:
            print("Couldn't get sonic session info")
            rc = 1
            output = {}
        return rc, output

    def get_dynamic_info(self):
        """
        Implementation for getting the SONiC info for SONiC regression runs.
        Currently it will get the following:
            1. version
            2. platform
            3. hwsku
            4. asic
            5. topology
            6. chip_type
            7. branch

        @return:
            Tuple with return code and dictionary of additional info to add.
        """
        print("Run SonicAddSessionInfo.get_dynamic_info")

        topo_api = TopologyAPI(self.conf_obj.setup_info['topology_file'])
        topo_hosts = topo_api.get_all_hosts()
        sonic_mgmt_host = next((host for host in topo_hosts if topo_api.get_object_attribute(host, 'ID') == 'SONIC_MGMT'), None)
        if sonic_mgmt_host is None:
            print('Failed to find the SONIC_MGMT player in topology file.')
            rc = 1
            output = {}
            return rc, output
        sonic_mgmt_ip = topo_api.get_object_attribute(sonic_mgmt_host, 'BASE_IP')
        sonic_mgmt_rpc_port = int(topo_api.get_object_attribute(sonic_mgmt_host, 'RPC_PORT') or DEFAULT_RPC_PORT)

        remote_workspace = '/root/mars/workspace'
        if not remote_workspace:
            logger.error("'sonic_mgmt_workspace' must be defined in extra_info section of setup conf")
            return (1, {})
        print("remote_workspace={0}".format(str(remote_workspace)))

        repo_name = self.conf_obj.get_extra_info().get("sonic_mgmt_repo_name")
        topology = self.conf_obj.get_extra_info().get("topology")
        setup_name = self.conf_obj.get_extra_info().get("setup_name")
        ngts_script_path = "ngts/scripts/sonic_add_session_info/test_sonic_add_session_info.py"
        script_cmd = ("PYTHONPATH=/devts:{REMOTE_WORKSPACE}/{REPO_NAME}/ /ngts_venv/bin/pytest -p "
                  "no:ngts.tools.conditional_mark -p no:ngts.tools.loganalyzer -p "
                  "no:ngts.tools.loganalyzer_dynamic_errors_ignore.la_dynamic_errors_ignore --setup_name={SETUP_NAME} "
                  "--sonic-topo={TOPOLOGY} --sonic_session_facts_prefix={SONIC_SESSION_FACTS_PREFIX} --log-level=INFO "
                  "--clean-alluredir --alluredir=/tmp/allure-results --showlocals {REMOTE_WORKSPACE}/{REPO_NAME}/{"
                  "NGTS_SCRIPT_PATH} ")
        script_cmd = script_cmd.format(REMOTE_WORKSPACE=remote_workspace, REPO_NAME=repo_name, TOPOLOGY=topology,
                               SETUP_NAME=setup_name, SONIC_SESSION_FACTS_PREFIX=SONIC_SESSION_FACTS_PREFIX,
                               NGTS_SCRIPT_PATH=ngts_script_path)
        print("script_cmd={0}".format(script_cmd))
        print("SONIC_MGMT IP={0}, RPC_PORT={1}".format(sonic_mgmt_ip, sonic_mgmt_rpc_port))
        try:
            conn = RemoteRPC(server_name=sonic_mgmt_ip, port=sonic_mgmt_rpc_port)
            conn.import_module("os")
            conn.import_module("mlxlib.common.execute")

            conn.modules.os.chdir(os.path.join(remote_workspace, repo_name, "ansible"))
            conn.modules.os.environ["HOME"] = "/root"

            p = conn.modules.execute.run_process(script_cmd, shell=True)
            (rc, output) = conn.modules.execute.wait_process(p)
            print("rc={0}".format(str(rc)))

            if rc != 0:
                print("Execute command failed!")
                return (1, {})
            rc, output = self._parse_dict_string_from_output(output)
        except Exception as e:
            rc = 1
            output = {}
            print("An error occurred:{0}".format(str(e)))
        finally:
            return (rc, output)
