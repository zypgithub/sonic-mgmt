import paramiko
import time
import scp
import json
import logging

from tests.common.fixtures.conn_graph_facts import conn_graph_facts, fanout_graph_facts  # noqa F401

logger = logging.getLogger(__name__)

dut_snake_config_name = "/tmp/dut_snake_config_db.json"
fanout_snake_sonic_config_name = "/tmp/fanout_snake_config.json"


def ssh_client(host, user, passwd):
    dut_client = paramiko.SSHClient()
    dut_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    dut_client.connect(host, 22, user, passwd, allow_agent=False)
    scp_client = scp.SCPClient(dut_client.get_transport())
    return dut_client, scp_client


def onyx_cmd(client, commands):
    com = "cli -h {}".format(" ".join(["\"{}\"".format(x) for x in commands]))
    stdin, stdout, stderr = client.exec_command(com, get_pty=True)
    stdout.read()


def fanout_port(sonic_port):
    pstr = sonic_port.replace("etp", "")
    sub_id = int(pstr[-1], 16) - 9  # Convert a, b, c, d into 1, 2, 3, 4 etc.

    if sub_id > 0:  # Was that last character a letter?
        p_id = int(pstr[0:-1])  # If so, parse as split port
        return "1/{}/{}".format(p_id, sub_id)
    else:
        p_id = int(pstr)  # If not parse entire string as port id
        return "1/{}".format(p_id)


def get_sku(duthost, sku, file_name):
    logger.info("Generating SONiC configuration from SKU")
    duthost.shell(f"sonic-cfggen --preset l2 -p -H -k {sku} > {file_name}")
    time.sleep(5)
    duthost.fetch(src=file_name, dest=file_name, flat=True)
    time.sleep(5)

    with open(file_name, "r") as f:
        return json.load(f)


def gen_fanout_config(
        fanout, fanout_sku, dut_config, fanout_port_to_speed_map, module_type,
        fan_vlan_map, fan_vrf_map, fan_route, vlan_count, **kwargs):
    if fanout.os == "onyx":
        gen_onyx_fanout_config(dut_config, module_type, fan_vlan_map, fan_vrf_map, fan_route, vlan_count)
    else:
        fanout_sonic_original_config = get_sku(fanout, fanout_sku, fanout_snake_sonic_config_name)
        gen_sonic_fanout_config(fanout_sonic_original_config, fanout_port_to_speed_map, fan_vlan_map, fan_vrf_map, fan_route)


def gen_onyx_fanout_config(sku_dat, module_type, fan_vlan_map, fan_vrf_map, fan_route, vlan_count, **kwargs):
    logger.info("Generating ONYX Configuration")
    splits = {}
    speeds = {}
    vlans = {}

    for port, dat in fan_vlan_map.items():
        fullname = dat[0]
        vid = dat[1]
        pids = fullname.split("/")

        # Update / add split
        if len(pids) > 2:
            portname = "/".join(pids[0:-1])
            splitnum = int(pids[-1])
            if splitnum > 4:
                max_split = 8
            elif splitnum > 2:
                max_split = 4
            else:
                max_split = 2
            splits[portname] = max(splits.get(portname, 0), max_split)

        speeds[fullname] = int(sku_dat["PORT"][port]["speed"]) // 1000
        vlans[fullname] = vid

    onyx_config = []

    onyx_config += ["no cli default prefix-modes enable"]
    onyx_config += ["interface {} module-type {}-split-{} force".format(p, module_type, s) for p, s in splits.items()]
    onyx_config += [""]
    onyx_config += ["interface {} speed {}G no-autoneg force".format(p, s) for p, s in speeds.items()]
    onyx_config += [""]
    onyx_config += ["vlan 100-{}".format(vlan_count)]
    onyx_config += ["interface {} switchport access vlan {}".format(p, v) for p, v in vlans.items()]
    onyx_config += [""]
    onyx_config += ["vrf definition {}".format(vrf) for vrf in set([vrf[0] for vlan, vrf in fan_vrf_map.items()])]
    onyx_config += ["vrf definition mgmt"]
    onyx_config += ["vrf definition {} rd 10.10.10.10:{}".format(vrf, vrf) for vrf in set([vrf[0] for vlan, vrf in fan_vrf_map.items()])]
    onyx_config += ["ip routing vrf {}".format(vrf) for vrf in set([vrf[0] for vlan, vrf in fan_vrf_map.items()])]
    onyx_config += ["interface vlan {} vrf forwarding {}".format(vlan, vrf[0]) for vlan, vrf in fan_vrf_map.items()]
    onyx_config += ["interface vlan {} ip address {}/24 primary".format(vlan, vrf[1]) for vlan, vrf in fan_vrf_map.items()]
    onyx_config += ["ip route vrf {} {}/24 {}".format(route["vrf"], route["prefix"], route["nexthop"]) for route in fan_route]

    onyx_config += ["cli default prefix-modes enable"]

    with open("onyx-config", "w") as f:
        f.writelines(["{}\n".format(l) for l in onyx_config])


def gen_sonic_fanout_config(sku_dat, fanout_port_to_speed_map, fan_vlan_map, fan_vrf_map, fan_route, **kwargs):
    logger.info("Generating SONiC fanout Configuration")
    sku_dat["VLAN"] = {}
    sku_dat["VLAN_MEMBER"] = {}

    for _, fan_port_valn_data in fan_vlan_map.items():
        fan_port = fan_port_valn_data[0]
        vlan = fan_port_valn_data[1]
        sku_dat["VLAN"].update({
            "Vlan{}".format(vlan): {"vlanid": str(vlan)}
        })
        sku_dat["VLAN_MEMBER"].update({
            "Vlan{}|{}".format(vlan, fan_port): {"tagging_mode": "untagged"}
        })

    sku_dat["VLAN_INTERFACE"] = {}
    sku_dat["VRF"] = {}
    for vlan, vrf in fan_vrf_map.items():
        sku_dat["VLAN_INTERFACE"].update({
            "Vlan{}".format(vlan): {"vrf_name": "Vrf{}".format(vrf[0])}
        })
        sku_dat["VLAN_INTERFACE"].update({
            "Vlan{}|{}/24".format(vlan, vrf[1]): {}
        })
        sku_dat["VRF"].update({"Vrf{}".format(vrf[0]): {}})

    sku_dat["STATIC_ROUTE"] = {}
    for route in fan_route:
        sku_dat["STATIC_ROUTE"].update({
            "Vrf{}|{}/24".format(route["vrf"], route["prefix"]): {
                "blackhole": "false",
                "distance": "0",
                "ifname": "",
                "nexthop": route["nexthop"],
                "nexthop-vrf": "Vrf{}".format(route["vrf"])
            }
        })

    logger.info("update fanout port's speed")
    for port, _ in sku_dat['PORT'].items():
        if port in fanout_port_to_speed_map:
            sku_dat["PORT"][port]["speed"] = fanout_port_to_speed_map[port]

    with open(fanout_snake_sonic_config_name, "w") as f:
        json.dump(sku_dat, f, indent=4)


def gen_sonic_dut_config(sku_dat, dut_port_to_speed_map, dut_vlan_map, dut_vrf_map, dut_route, **kwargs):
    logger.info("Generating SONiC Configuration")
    sku_dat["VLAN"] = {}
    sku_dat["VLAN_MEMBER"] = {}

    for port, vlan in dut_vlan_map.items():
        sku_dat["VLAN"].update({
            "Vlan{}".format(vlan): {"vlanid": str(vlan)}
        })
        sku_dat["VLAN_MEMBER"].update({
            "Vlan{}|{}".format(vlan, port): {"tagging_mode": "untagged"}
        })

    sku_dat["VLAN_INTERFACE"] = {}
    sku_dat["VRF"] = {}
    for vlan, vrf in dut_vrf_map.items():
        sku_dat["VLAN_INTERFACE"].update({
            "Vlan{}".format(vlan): {"vrf_name": "Vrf{}".format(vrf[0])}
        })
        sku_dat["VLAN_INTERFACE"].update({
            "Vlan{}|{}/24".format(vlan, vrf[1]): {}
        })
        sku_dat["VRF"].update({"Vrf{}".format(vrf[0]): {}})

    sku_dat["STATIC_ROUTE"] = {}
    for route in dut_route:
        sku_dat["STATIC_ROUTE"].update({
            "Vrf{}|{}/24".format(route["vrf"], route["prefix"]): {
                "blackhole": "false",
                "distance": "0",
                "ifname": "",
                "nexthop": route["nexthop"],
                "nexthop-vrf": "Vrf{}".format(route["vrf"])
            }
        })

    logger.info("update dut port's speed")
    for port, port_info in sku_dat['PORT'].items():
        if port in dut_port_to_speed_map:
            sku_dat["PORT"][port]["speed"] = dut_port_to_speed_map[port]

    with open(dut_snake_config_name, "w") as f:
        json.dump(sku_dat, f, indent=4)


def generate_vlans(sku_dat, dut_port_to_fanout_port_map, request):
    logger.info("Generating snake configuration")

    dut_vlan_map = {}
    fan_vlan_map = {}

    dut_vrf_map = {}
    fan_vrf_map = {}

    # List of routes with keys vrf / nexthop / prefix
    dut_route = []
    fan_route = []

    vlan_count = 100
    vrf_count = 0

    out_port = 0
    on_dut = True
    last = False

    dut_ports = list(sku_dat["PORT"].keys())
    dut_ports.sort(key=lambda x: int(x.replace("Ethernet", "")))

    snake_test_port_num = request.config.getoption("--snake_test_port_num")
    if snake_test_port_num > 0:
        last_port_index = snake_test_port_num - 2
    else:
        last_port_index = len(dut_ports) - 2
    assert last_port_index + 2 <= len(dut_port_to_fanout_port_map), \
        f"The tested port number:{last_port_index + 2} is greater than " \
        f"the port number of actual port connection:{len(dut_port_to_fanout_port_map)}." \
        f"Please specify the port number by snake_test_port_num according to the port cable connection number "

    dut_vrf_map.update({vlan_count: (vrf_count, "10.5.0.1")})
    dut_route.append({"vrf": vrf_count, "nexthop": "10.5.0.2"})
    vrf_count += 1

    for i, p in enumerate(dut_ports):

        op = dut_port_to_fanout_port_map[p]

        fan_vlan_map.update({
            dut_ports[i]: (op, vlan_count),
        })
        dut_vlan_map.update({
            dut_ports[i]: vlan_count,
        })

        if last: break

        if on_dut:
            fan_vrf_map.update({
                vlan_count: (vrf_count, "10.5.{}.2".format(vlan_count - 100)),
                vlan_count + 1: (vrf_count, "10.5.{}.2".format(vlan_count - 99))
            })
            fan_route += [
                {"vrf": vrf_count, "nexthop": "10.5.{}.1".format(vlan_count - 100), "prefix": "10.5.0.0"},
                {"vrf": vrf_count, "nexthop": "10.5.{}.1".format(vlan_count - 99)}
            ]
            on_dut = False

            if last_port_index == i:
                last = True
        else:
            dut_vrf_map.update({
                vlan_count: (vrf_count, "10.5.{}.1".format(vlan_count - 100)),
                vlan_count + 1: (vrf_count, "10.5.{}.1".format(vlan_count - 99)),
            })
            dut_route += [
                {"vrf": vrf_count, "nexthop": "10.5.{}.2".format(vlan_count - 100), "prefix": "10.5.0.0"},
                {"vrf": vrf_count, "nexthop": "10.5.{}.2".format(vlan_count - 99)}
            ]
            on_dut = True
            vrf_count += 1

        vlan_count += 1

    dut_vrf_map.update({vlan_count: (vrf_count, "10.5.{}.1".format(vlan_count - 100))})
    dut_route.append({"vrf": vrf_count, "nexthop": "10.5.{}.2".format(vlan_count - 100), "prefix": "10.5.0.0"})

    for route in dut_route + fan_route:
        if "prefix" not in route:
            route["prefix"] = "10.5.{}.0".format(vlan_count - 100)

    return {"dut_vlan_map": dut_vlan_map,
            "fan_vlan_map": fan_vlan_map,
            "dut_vrf_map": dut_vrf_map,
            "fan_vrf_map": fan_vrf_map,
            "dut_route": dut_route,
            "fan_route": fan_route,
            "vlan_count": vlan_count}
