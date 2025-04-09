import logging

logger = logging.getLogger()


def generic_sonic_output_parser(output, headers_ofset=0, len_ofset=1, data_ofset_from_start=2,
                                data_ofset_from_start_end=None, data_ofset_from_end=None,
                                column_ofset=2, output_key=None, header_line_number=1):
    """
    This method doing parse for command output and provide dictionary or list of dictionaries with parsed results.
    Method works only in case when cmd output has structure like below
    :param output: command output which should be parsed, example:
    Capability codes: (R) Router, (B) Bridge, (O) Other                                                 <<< This line we can skip by ofset args
    LocalPort    RemoteDevice             RemotePortID       Capability    RemotePortDescr              <<< Mandatory line
    -----------  -----------------------  -----------------  ------------  -------------------------    <<< Mandatory line
    Ethernet0    r-sonic-10-006           0c:42:a1:88:0a:1c  R             Interface   8 as enp5s0f0
    :param headers_ofset: Line number in which we have headers, in example above it is line 1(in real it is 2, but in python it is 1)
    :param len_ofset: Line number from which we can find len for all fields, in example above it is line 2
    :param data_ofset_from_start: Line number from which we will start parsing data and fill dictionary with results
    :param data_ofset_from_start_end: Line number from start till which we will do parse(parameter is optional)
    :param data_ofset_from_end: Line number from end till which we will do parse(parameter is optional)
    :param column_ofset: Number of spaces between columns in output(usually 2)
    :param output_key: parameter which specify which key should be used in output(from example above can be used: LocalPort,
    RemoteDevice, RemotePortID, Capability, RemotePortDescr). If NONE - than we we will return list
    :param header_line_number: the number of the header lines, usually the number is 1, but for some command, it will be more than 1
    :return: dictionary, example for output of "show lldp table" with args for method: headers_ofset=1,
                                                                                       len_ofset=2,
                                                                                       data_ofset_from_start=3,
                                                                                       data_ofset_from_end=-2,
                                                                                       output_key='LocalPort'
    {'Ethernet0': {'LocalPort': 'Ethernet0', 'RemoteDevice': 'r-sonic-10-006', ' RemotePortID': '0c:42:a1:88:0a:1c',
    ' Capability': 'R', 'RemotePortDescr': 'Interface   8 as enp5s0f0'}, 'Ethernet8': {'LocalPort': 'Ethernet8',
    'RemoteDevice': 'r-ocelot-02',...................}}
    Or LIST can be returned, example: [{'LocalPort': 'Ethernet0', 'RemoteDevice': 'r-sonic-10-006',
    ' RemotePortID': '0c:42:a1:88:0a:1c', ' Capability': 'R', 'RemotePortDescr': 'Interface   8 as enp5s0f0'},
    {'LocalPort': 'Ethernet8', 'RemoteDevice': 'r-ocelot-02',........}]
    """
    # Get all headers
    headers_lines = output.splitlines()[
        headers_ofset: headers_ofset +
        header_line_number]

    """Get lens for each column according to "---------" symbols len in output
    Interface    Oper    Admin    Alias    Description
    -----------  ------  -------  -------  -------------    <<<<<< This will be used
    Ethernet0      up       up     etp1            N/A
    """
    column_lens = output.splitlines()[len_ofset].split()

    # Parse only lines from "data_ofset_from_start" and if
    # "data_ofset_from_end" exist - then parse till the "data_ofset_from_end"
    data = output.splitlines()[data_ofset_from_start:]
    if data_ofset_from_end and not data_ofset_from_start_end:
        data = output.splitlines()[data_ofset_from_start:data_ofset_from_end]
    if data_ofset_from_start_end and not data_ofset_from_end:
        data = output.splitlines()[data_ofset_from_start:data_ofset_from_start_end]

    result_dict = {}
    result_list = []
    last_line_key = ""
    for line in data:
        if line == '':
            continue
        first_column_item = line[:len(column_lens[0])].strip()
        if first_column_item:
            line_dict = {}
        parse_line_data_to_dict(line, line_dict, column_lens, headers_lines, column_ofset)
        if output_key:
            last_line_key = update_result_dict(line_dict, output_key, last_line_key, result_dict)
        elif first_column_item:
            result_list.append(line_dict)

    if output_key:
        return result_dict
    else:
        return result_list


def parse_line_data_to_dict(line, line_dict, column_lens, headers_lines, column_ofset):
    """
    Parse the line data from string to the dict, the line data will be updated to line_dict.
    :param line: the origin line data in string format
    :param line_dict: dictionary which is used to save the data in the line in string format
    :param column_lens: the column length list
    :param headers_lines: the headers name content
    :param column_ofset: Number of spaces between columns in output(usually 2)
    :return: None
        Example: the line can be one of line of the following content, for the RULE_1, it has more than one line,
        in this function need to do the special process of it.
            Table                  Rule    Priority    Action    Match
            ---------------------  ------  ----------  --------  --------------------------
            DATA_EGRESS_L3TEST     RULE_1  9999        FORWARD   ETHER_TYPE: 2048
                                                                 SRC_IP: 30.0.0.2/32
            DATA_EGRESS_L3V6TEST   RULE_1  9999        FORWARD   SRC_IPV6: 80c0:a800::2/128
    """
    base_position = 0
    for column_len in column_lens:
        new_position = base_position + len(column_len)
        header_name = get_column_header_name(headers_lines, base_position, new_position)
        item_value = line[base_position:new_position].strip()
        if header_name in line_dict:
            # if line_dict has header_name, it means that one item occupy more than one line,
            # then the corresponding value should be a list
            if item_value:
                if not isinstance(line_dict[header_name], list):
                    line_dict[header_name] = [line_dict[header_name]]
                line_dict[header_name].append(item_value)
        else:
            line_dict[header_name] = item_value
        base_position = new_position + column_ofset
    return line_dict


def get_column_header_name(headers_lines, base_position, new_position):
    """
    get the full column header name
    :param headers_lines: how many lines of the header content
    :param base_position: start position of the column header
    :param new_position: end position of the column header
    :return: column header name
    """

    header_name = ""
    for headers_line in headers_lines:
        tmp = headers_line[base_position:new_position].strip()
        if tmp:
            if header_name:
                header_name = header_name + " " + \
                    headers_line[base_position:new_position].strip()
            else:
                header_name = tmp
    return header_name


def update_result_dict(line_dict, key_name, last_line_key, result_dict):
    """
    update the result dict
    :param line_dict: dict format value of one line in the return of the show command
    :param key_name: the output key of the result dict, it is one of the column header name
    :param last_line_key: the key value used in the previous line.
    :param result_dict: the result dict which need to be updated
    :return: the output key value
    """
    if line_dict[key_name]:
        # if the corresponding column value is not empty, then it should be the
        # first line of the value
        line_key = line_dict[key_name]
        result_dict[line_key] = line_dict
    else:
        # if the corresponding column value is empty, then it should be not
        # first line of the value
        last_line_dict = result_dict[last_line_key]
        line_key = last_line_key

        for key in last_line_dict.keys():
            if line_dict[key]:
                last_line_dict[key] = " ".join([last_line_dict[key], line_dict[key]])
    return line_key


def parse_show_interfaces_transceiver_eeprom(interfaces_transceiver_eeprom_output):
    """
    Parse output of command: 'show interfaces transceiver eeprom' as dictionary
    :param interfaces_transceiver_eeprom_output: output of command: 'show interfaces transceiver eeprom'
    Example:
    Ethernet47: SFP EEPROM is not applicable for RJ45 port

    Ethernet48: SFP EEPROM detected
            Application Advertisement: N/A
            Connector: No separable connector
            Encoding: 64B66B
            Extended Identifier: Power Class 1(1.5W max)
            Extended RateSelect Compliance: QSFP+ Rate Select Version 1
            Identifier: QSFP28 or later
            Length Cable Assembly(m): 1
            Nominal Bit Rate(100Mbs): 255
            Specification compliance:
                    10/40G Ethernet Compliance Code: 40GBASE-CR4
                    Extended Specification compliance: 25GBASE-CR CA-25G-N or 50GBASE-CR2 with no FEC
            Vendor Date Code(YYYY-MM-DD Lot): 2020-06-15
            Vendor Name: Mellanox
            Vendor OUI: 00-02-c9
            Vendor PN: MCP1600-C01AE30N
            Vendor Rev: A4
            Vendor SN: MT2032VS01693

    :return: dict, example: {'Ethernet47': {'Status': 'SFP EEPROM is not applicable for RJ45 port'},
                             'Ethernet48': {'Status': 'SFP EEPROM detected',
                                            'Application Advertisement': 'N/A',
                                            'Connector': 'No separable connector'...}}
    """
    result = {}
    port = None
    base_dict_key = None

    for line in interfaces_transceiver_eeprom_output.splitlines():
        if line:
            num_of_spaces_at_the_begining = len(line) - len(line.lstrip())
            split_line = line.split(': ')

            # if 0 spaces at the beginning - means that it's interface definition line - will get port name from it
            if num_of_spaces_at_the_begining == 0 and len(split_line) == 2:
                port, status = split_line
                result[port] = {'Status': status}

            # if number of spaces 8 - means that this line contain key: value
            if num_of_spaces_at_the_begining == 8:
                # If split_line len 2 - then we have key and value
                if len(split_line) == 2:
                    dict_key, dict_data = split_line
                # if split_line len not 2 - then we have only key and nested dict, which will have key: value below
                else:
                    # get key of nested dict and put empty dict as data
                    dict_key = split_line[0]
                    base_dict_key = dict_key.strip()
                    dict_data = {}

                data_dict = {dict_key.strip(): dict_data}
                result[port].update(data_dict)

            # if number of spaces 8 - means that this line contain nested dict data
            if num_of_spaces_at_the_begining == 16:
                dict_key, dict_data = split_line
                data_dict = {dict_key.strip(): dict_data}
                result[port][base_dict_key].update(data_dict)

    return result
