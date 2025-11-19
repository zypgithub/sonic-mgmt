import logging
import allure
import os
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.helpers.object_filters import filter_objects
logger = logging.getLogger()


def test_stop_and_remove_nvos_simx_docker(topology_obj):
    dut_name, server_engine = get_topo_info(topology_obj)
    stop_and_remove_reg_simx_docker(dut_name, server_engine)
    stop_all_nvos_simx_dockers(server_engine)


def test_stop_and_remove_reg_simx_docker(topology_obj):
    for player_name, player in filter_objects(topology_obj.players, host_type='dut', engine_type='ssh').items():
        dut_name = player['attributes'].noga_query_data['attributes']['Common']['Name']
        server_name = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific'][
            'serial_conn_command'].split()[1]
        server_engine = ConnectionTool.create_ssh_conn(server_name, os.getenv("TEST_SERVER_USER"),
                                                       os.getenv("TEST_SERVER_PASSWORD")).returned_value
        stop_and_remove_reg_simx_docker(dut_name, server_engine)


def get_topo_info(topology_obj):
    with allure.step("Get server and dut details"):
        dut_name = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Common']['Name']
        server_name = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific'][
            'serial_conn_command'].split()[1]
        server_engine = ConnectionTool.create_ssh_conn(server_name, os.getenv("TEST_SERVER_USER"),
                                                       os.getenv("TEST_SERVER_PASSWORD")).returned_value
        return dut_name, server_engine


def stop_and_remove_reg_simx_docker(dut_name, server_engine):
    with allure.step("Check docker id"):
        docker_info = server_engine.run_cmd("sudo docker ps -a | grep {}".format(dut_name))
        if docker_info:
            docker_id = docker_info.split()[0]
            logging.info("Simx docker id: {}".format(docker_id))

            with allure.step("Stop NVOS simx docker for {}".format(dut_name)):
                output = server_engine.run_cmd("sudo docker stop {}".format(docker_id))
                if docker_id not in output:
                    logging.warning(f"Failed to stop simx docker. Output: {output}")

                with allure.step("Stop NVOS simx docker for {}".format(dut_name)):
                    output = ""
                    try:
                        output = server_engine.run_cmd("sudo docker rm -f {}".format(docker_id))
                        assert not output or "Error" not in output, f"Failed to remove simx docker. Error: {output}"
                    except BaseException as ex:
                        raise Exception(f"Failed to remove simx docker.\nError: {output}\nException: {ex}")
        else:
            logging.info("Simx docker is not running for {} - nothing to stop".format(dut_name))


def stop_all_nvos_simx_dockers(server_engine):
    try:
        with allure.step("Stop all SIMX dockers on current server"):
            dockers_info = server_engine.run_cmd("sudo docker ps")
            docker_info_list = dockers_info.split()[1:]
            for docker_info in docker_info_list:
                if NvosConst.SERVERS_USER_NAME not in docker_info:
                    docker_id = docker_info.split()[0]
                    with allure.step(f"Stop docker id {docker_id}"):
                        output = server_engine.run_cmd("sudo docker stop {}".format(docker_id))
                        if docker_id not in output:
                            logging.warning(f"Failed to stop simx docker {docker_id}")
    except Exception as err:
        logging.warning(f"Failed to stop simx dockers: {str(err)}")
