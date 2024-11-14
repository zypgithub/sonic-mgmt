class DvsPerformance:
    def __init__(self, topology_obj):
        self.topology_obj = topology_obj

    '''
    TODO :- Shahaf Bodner
    Implement the following methods exactly as defined,
    Tests would be dependent upon these methods therefore any change in the method call
    should be translated into equivalent for sonic and cumulus(NVUE)
    '''

    def get_ports(self, ports_dict):
        '''
        For performance setups only, gets the physical and sdk ports.
        This assumes the following physical topology :-
        LEFT_TG (First 32 ports) ---- (First 32 ports) DUT (Last 32 ports) ---- (Last 32 Ports) RIGHT_TG

        :param ports_dict: dictionary containing the following arguments :-
            split_upstream : 1x or 2x or 4x or 8x
            split_downstream : 1x or 2x or 4x or 8x
            port_sku : HW_SKU for moose devices.

        :param get_sdk_ports: bool: Whether or not we want to set the sdk ports.

        returns 2 dictionaries phy_port_dict, sdk_port_dict
        phy_port_dict = {
            'right_tg' : [],
            'left_tg' : [],
            'dut' : []
        }
        sdk_port_dict = {
            'right_tg' : [],
            'left_tg' : [],
            'dut' : []
        }
        TODO :- Shahaf Bodner
        return
        fanout left ---- [10001, 10004, 10008 ........]
        dut -------- [10001, 10003, ..........., 100dd, ....., 100ff]
        fanout right [10001, 10003, 10004, 10007]
        800G <-> 400G
        Args: split_upstream : 1x
                split_downstream: 2x
        '''
        raise NotImplementedError

    '''
    Define a set_port_breakout to fix the port breakout on a single dut
    def set_port_breakout()
    '''

    def get_sdk_port_from_physical_ports(self, engine, physical_port):
        '''
        Since SDK ports are same as physical ports this function should just return the list of sdk port only.
        In case of DVS we would treat the sdk ports and physical ports as same.
        '''
        return physical_port

    def apply_configuration(self, parameter_dict, scenario, switch_name, template_suite="/performance_tests/performance_config_templates/"):
        '''
        TODO :- Shahaf Bodner
        Take the parameter dictionary and generate a dvs based configuration
        '''
        raise NotImplementedError
