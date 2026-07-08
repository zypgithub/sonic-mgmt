import logging
import time
from devts.infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker

logger = logging.getLogger()


def send_traffic(player, sender, sender_intf, sender_pkt_format, sender_count):
    """
    This method is used ot send traffic
    """
    logger.info("Start traffic")
    validation_r = {'sender': sender,
                    'send_args': {'interface': sender_intf,
                                  'packets': sender_pkt_format,
                                  'count': sender_count}}
    scapy_sender = ScapyChecker(player, validation_r)
    scapy_sender.run_validation()
    logger.info("Send traffic action end")


def start_sniffer(engines, host_intf_pair, pcap_path_format='/tmp/tmp_{}.pcap', direction="in"):
    """
    Start tcpdump sniffer
    """
    logger.info("Tcpdump sniffer starting")
    for host, intf in host_intf_pair.items():
        logging.info(f"Tcpdump sniffer starting on:{host} interface:{intf} direction:{direction}")
        cmd = f"nohup sudo tcpdump -i {intf} -w {pcap_path_format.format(host)} --direction {direction} -U &"
        engine = engines.dut
        if host == 'ha':
            engine = engines.ha
        if host == 'hb':
            engine = engines.hb
        engine.run_cmd(cmd)


def stop_sniffer(engines, host_intf_pair, pcap_path_format='/tmp/tmp_{}.pcap'):
    """
    Stop tcpdump sniffer
    :return:
    """
    cmd = "sudo killall -s SIGINT tcpdump"
    time.sleep(2)  # Wait for  tcpdump packet processing
    logger.info("Tcpdump sniffer stopping")
    for host, intf in host_intf_pair.items():
        pcap_path = pcap_path_format.format(host)
        engine = engines.dut
        if host == 'ha':
            engine = engines.ha
        if host == 'hb':
            engine = engines.hb
        logger.info(f"Stop tcpdump sniffer at {host}")
        engine.run_cmd(cmd)
        out = engine.run_cmd(f'ls -l {pcap_path}', validate=False)
        if "No such file" in out:
            logger.info(f"No packet captured at {host}")
            continue
        logger.info(f"Copy {pcap_path} from {host} to ngts docker")
        engine.copy_file(source_file=pcap_path, dest_file=pcap_path, file_system='/', direction="get",
                         overwrite_file=True, verify_file=False)
        engine.run_cmd(f"rm -f {pcap_path}")
