from typing import Literal, Optional


def filter_objects(
        players: dict, *,
        host_type: Literal["dut", "mgmt"] = None,
        engine_type: Optional[Literal["serial", "ssh"]] = None
):
    """
    Player filter function, useful for multiple duts/devices/players.
    :param players: dictionary of players
    :param host_type: filters by host type, if not provided, will get all types.
    :param engine_type: filters by engine type, if not provided, will get all types.
    :return: filtered players
    """
    filtered = {}

    for p_name, p in players.items():
        is_ssh = not p_name.endswith("serial")  # we have 2 options serial/ssh

        # host_type filter
        if host_type is not None and host_type not in p_name:
            continue

        # engine_type filter
        if engine_type is not None and (engine_type == "ssh" and not is_ssh or engine_type == "serial" and is_ssh):
            continue

        filtered[p_name] = p

    return dict(sorted(filtered.items()))
