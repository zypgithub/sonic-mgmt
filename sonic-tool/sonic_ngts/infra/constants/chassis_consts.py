
class ChassisConst:
    ANACONDA = 'anaconda'
    LIONFISH = 'lionfish'
    LEOPARD = 'leopard'
    PANTHER = 'panther'
    TIGON = 'tigon'
    MOOSE = 'moose'
    BOBCAT = 'bobcat'
    BISON = 'bison'
    GAUR = 'gaur'
    '''
    the MAIN_FRU_DIC conatains all the information about a new machine and is orgzinized as such-
    MAIN_FRU_DIC[ChassisConst.<system_type>] = {'fru': list of the FRUs of the system type, with and without initials
                               'port_number': the port number in this system_type,
                               'chip_type': }
    '''
    MAIN_FRU_DIC = dict()

    MAIN_FRU_DIC[TIGON] = {'fru': ['4600C'],
                           'port_number': 64,
                           'chip_type': "SPC3"
                           }


    MAIN_FRU_DIC[PANTHER] = {'fru': ['2700'],
                             'port_number': 32,
                             'chip_type': "SPC"
                             }


    MAIN_FRU_DIC[ANACONDA] = {'fru': ['3700', '3700C'],
                              'port_number':  32,
                              'chip_type': "SPC2"
                              }


    MAIN_FRU_DIC[LIONFISH] = {'fru': ['3420'],
                              'port_number':  60,
                              'chip_type': "SPC2"
                              }

    MAIN_FRU_DIC[LEOPARD] = {'fru': ['4700'],
                             'port_number':  32,
                             'chip_type': "SPC3"
                             }

    MAIN_FRU_DIC[MOOSE] = {'fru': ['5600'],
                           'port_number':  64,
                           'chip_type': "SPC4"
                           }

    MAIN_FRU_DIC[BOBCAT] = {'fru': ['4280'],
                           'port_number': 28,
                           'chip_type': "SPC3"
                           }

    MAIN_FRU_DIC[BISON] = {'fru': ['5640'],
                           'port_number': 64,
                           'chip_type': "SPC5"
                           }

    MAIN_FRU_DIC[GAUR] = {'fru': ['5610N'],
                        'port_number': 64,
                        'chip_type': "SPC4"
                        }


    '''
    CHASSIS_TO_TYPE_DICT contains items in the structure of 'system_tye' : [FRU list for possible FRUs for the system]
    for example it may contain the lines:
        ...
        'jaguar': ['8700', 'MQM8700'],
        'mantaray': ['8500', 'CS8500'],
        'anaconda': ['3700', 'MSN3700', '370013', 'MSN3700C', '3700C'],
        'tigris': ['3800', 'MSN3800'],
        ...
    '''
    CHASSIS_TO_TYPE_DICT = {}
    for system_type, value in MAIN_FRU_DIC.items():
        CHASSIS_TO_TYPE_DICT[system_type] = value['fru']
