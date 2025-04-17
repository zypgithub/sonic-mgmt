import logging

from dotted_dict import DottedDict
from ngts.nvos_tools.Devices.EthDevice import Mlx2410Switch, Mlx4600Switch, Mlx4600cSwitch, Mlx4700Switch, \
    Mlx5600Switch, \
    Mlx5400Switch, Mlx4410Switch, Mlx3750sxSwitch, Mlx3700csSwitch, Mlx3700cSwitch, Mlx3420Switch, Mlx2700Switch, \
    Mlx2201Switch, Mlx2100Switch, \
    Mlx2010Switch, Mlx3700Switch
from ngts.nvos_tools.Devices.IbDevice import (GorillaSwitch, GorillaSwitchBF3, CrocodileSwitch, BlackMambaSwitch,
                                              CrocodileSimxSwitch, JulietScaleoutSwitch, JulietTTMSwitch,
                                              JulietNonScaleoutSwitch, JulietAriel, JulietNonScaleoutSwitchNoNCI,
                                              JulietArielPS, JulietNonScaleoutSwitchNoNCI5600, TaipanSingleAsicSwitch)

logger = logging.getLogger()


class DeviceFactory:
    device_type_dict = \
        {
            'MQM9700 - Gorilla Blackbird': GorillaSwitch,
            'MQM9700 - Gorilla BF3': GorillaSwitchBF3,
            'MQM9700': GorillaSwitch,
            'MSN3700': Mlx3700Switch,
            'MSN3700 - Anaconda': Mlx3700Switch,
            'Q3200-RA-Crocodile Sunbird': CrocodileSwitch,
            'QM3400': CrocodileSwitch,
            'QM3400 - Crocodile': CrocodileSwitch,
            'QM3400_simx - Crocodile': CrocodileSwitch,
            'QM8790 - Black Mamba': BlackMambaSwitch,
            'QM3000 - Black Mamba': BlackMambaSwitch,
            'Q3400-RA Black Mamba': BlackMambaSwitch,
            'Q3400-RA Black_Mamba': BlackMambaSwitch,
            'Mellanox SN5600': Mlx5600Switch,
            'Mellanox SN5400': Mlx5400Switch,
            'Mellanox SN4700': Mlx4700Switch,
            'Mellanox SN4600': Mlx4600Switch,
            'Mellanox SN4600c': Mlx4600cSwitch,
            'Mellanox SN4410': Mlx4410Switch,
            'Mellanox SN3750sx': Mlx3750sxSwitch,
            'Mellanox SN3700': Mlx3700Switch,
            'Mellanox SN3700cs': Mlx3700csSwitch,
            'Mellanox SN3700c': Mlx3700cSwitch,
            'Mellanox SN3420': Mlx3420Switch,
            'Mellanox 2700': Mlx2700Switch,
            'Mellanox 2410': Mlx2410Switch,
            'Mellanox 2201': Mlx2201Switch,
            'Mellanox 2100': Mlx2100Switch,
            'Mellanox 2010': Mlx2010Switch,
            'N5110_LD - JulietScaleout': JulietScaleoutSwitch,
            'N5110_LD - JulietTTM': JulietTTMSwitch,
            'N5100_LD - JulietNonScaleout': JulietNonScaleoutSwitch,
            'N5112_LD - JulietAriel': JulietAriel,
            'N5200_LD - JulietNonScaleoutSwitchNoNCI': JulietNonScaleoutSwitchNoNCI,
            'N5112_LD - JulietArielPS': JulietArielPS,
            'N5600_LD - JulietNonScaleoutSwitchNoNCI': JulietNonScaleoutSwitchNoNCI5600,
            'Q3450_LD - Taipan': TaipanSingleAsicSwitch
        }

    @staticmethod
    def create_device(device_name):
        try:
            if device_name not in DeviceFactory.device_type_dict.keys():
                if "5600" in device_name:
                    device_name = 'Mellanox SN5600'
                elif "4600C" in device_name:
                    device_name = 'Mellanox SN4600c'
                else:
                    device_name = device_name[0:7]
            instance_type = DeviceFactory.device_type_dict[device_name]
            instance = instance_type()
            logger.info('Received switch type {device_name}, created Device instance {instance_type}'.format(
                device_name=device_name, instance_type=str(instance_type)))
            return instance
        except Exception:
            logger.error("please configure device_name = %s", device_name)
            raise

    @staticmethod
    def create_devices_object(topology_obj):
        device_objects = DottedDict()
        dut_name = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific'][
            'switch_type']
        device_objects.dut = DeviceFactory.create_device(dut_name)
        return device_objects
