import logging
import traceback
from typing import Dict

import pytest

from infra.tools.general_constants.constants import NogaConstants
from infra.tools.topology_tools import nogaq
import requests_cache
from ngts.constants.constants import SerialLoggerConst
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from .SerialLogAnalyzer import SerialLogAnalyzer, DUTHOSTS_MISSING_MESSAGE
from ..serial_log_script import get_all_ips_in_setup


@pytest.fixture()
def serial_log_analyzers(request, test_name, setup_name, session_id, tmp_path) -> Dict[str, SerialLogAnalyzer]:
    mode = request.config.getoption(SerialLoggerConst.CMD_LINE_KEY)
    logging_active = (mode != SerialLoggerConst.MODE_OFF)
    ips = get_all_ips_in_setup(setup_name)
    logging.info(f"IPs in setup: {ips}")
    analyzers = DefaultDict(lambda ip: SerialLogAnalyzer(logging_active, test_name, setup_name, session_id, tmp_path,
                                                         request, ip, can_analyze=False))
    for ip in ips:
        analyzers[ip] = SerialLogAnalyzer(logging_active, test_name, setup_name, session_id, tmp_path, request, ip)

    yield analyzers

    ip_to_host = {}
    try:
        duthosts = request.getfixturevalue("duthosts")
        duthost_default = None  # when duthost is None we know there was an error and should raise an exception
        for host in filter(bool, duthosts):  # iterate duthosts elements except "None" objects
            data = nogaq.get_noga_resource_data(resource_name=host.hostname)
            ip = data[NogaConstants.ATTRIBUTES][NogaConstants.SPECIFIC][NogaConstants.IP]
            ip_to_host[ip] = host
    except pytest.FixtureLookupError:  # duthosts fixture unavailable for SONiC switches
        logging.info(DUTHOSTS_MISSING_MESSAGE + " Test and serial-log-analyzer will still run.")
        duthost_default = NotImplemented  # when duthost is NotImplemented we know we're on a non-NVOS system
    requests_cache.uninstall_cache()

    exceptions = []
    if mode in {SerialLoggerConst.MODE_ANALYZE, SerialLoggerConst.MODE_ANALYZE_AND_OPEN_BUGS}:
        for analyzer in analyzers.values():  # todo: instead of try/except, run them in parallel
            try:
                analyzer.analyze(ip_to_host.get(analyzer.target_ip, duthost_default),
                                 only_check=(mode == SerialLoggerConst.MODE_ANALYZE))
            except Exception as e:
                exceptions.append((analyzer.target_ip, e, traceback.format_exc()))
    else:
        logging.warning(f"Serial log analyzer mode is set to '{mode}'. Not analyzing.")

    if exceptions:
        msg = f"Errors in serial log analyzer on {len(exceptions)} hosts:"
        for (ip, exception, traceback_str) in exceptions:
            msg += (f"\n\nOn {ip} - {traceback_str}"
                    f"----------------------------------------------------------------------")
        raise Exception(msg)
