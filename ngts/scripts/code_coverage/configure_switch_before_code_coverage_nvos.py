import allure
import pytest

from ngts.ngts_types import EnginesT


@pytest.mark.disable_loganalyzer
@allure.title('Configure switch before code coverage')
def test_configure_switch_before_code_coverage(engines: EnginesT):
    try:
        with allure.step('Configure switch before code coverage'):
            engines.dut.run_cmd('sudo chmod 777 /sonic/src/sonic-swss-common/common/.libs/* /etc/default/nvued')
            engines.dut.run_cmd('echo "COVERAGE_PROCESS_START=/etc/python3/coverage_config" >> /etc/default/nvued')
            engines.dut.run_cmd('echo "COVERAGE_RCFILE=/etc/python3/coverage_config" >> /etc/default/nvued')
            engines.dut.run_cmd('echo "COVERAGE_FILE=/var/lib/python/coverage/raw" >> /etc/default/nvued')

    except Exception as err:
        raise AssertionError(err)
