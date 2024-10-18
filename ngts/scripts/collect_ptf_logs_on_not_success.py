import allure
import os
import time
import logging
import pytest

from infra.tools.general_constants.constants import DefaultTestServerCred
from ngts.constants.constants import SETUPS_WITH_NON_DEFAULT_PTF
logger = logging.getLogger()


@pytest.mark.disable_loganalyzer
def test_collect_ptf_logs(topology_obj, setup_name, dumps_folder, is_simx, is_air):
    if not (is_air or is_simx):
        ptf_log_file = 'ptf_logs.{}.tgz'.format(time.time_ns())
        dest_file = dumps_folder + '/' + ptf_log_file
        hyper_engine = topology_obj.players['hypervisor']['engine']
        hyper_engine.username = DefaultTestServerCred.DEFAULT_USERNAME
        hyper_engine.password = DefaultTestServerCred.DEFAULT_PASS
        ptf_docker_name = f'ptf_vm-t{2 if setup_name in SETUPS_WITH_NON_DEFAULT_PTF else 1}'
        try:
            with allure.step('Generate ptf log tar file {}'.format(ptf_log_file)):
                hyper_engine.run_cmd('docker exec {} tar -czvf /tmp/{} /tmp/'.format(ptf_docker_name, ptf_log_file))
                hyper_engine.run_cmd('docker cp {}:/tmp/{} /tmp'.format(ptf_docker_name, ptf_log_file))
                hyper_engine.run_cmd('docker exec {} rm /tmp/{}'.format(ptf_docker_name, ptf_log_file))
            with allure.step('Copy the ptf log tar file to log folder {}'.format(dumps_folder)):
                hyper_engine.run_cmd('sudo cp /tmp/{} {}'.format(ptf_log_file, dest_file))
                os.chmod(dest_file, 0o777)
                hyper_engine.run_cmd('rm /tmp/{}'.format(ptf_log_file))
            logger.info('Ptf log tar file location: {}'.format(dest_file))
        except Exception:
            logger.error('Failed to collect the ptf log files')
