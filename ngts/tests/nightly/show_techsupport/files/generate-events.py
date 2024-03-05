import sys
from random import random
from time import strftime, gmtime
from swsscommon.swsscommon import SonicV2Connector, ConfigDBConnector

# Check if an argument is provided. If not, set default value to 100
num_iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 100

state_db = SonicV2Connector(host='127.0.0.1')
state_db.connect(state_db.STATE_DB, False)

config_db = ConfigDBConnector()
config_db.connect()

severities = ['fatal']

for severity in severities:
    for i in range(num_iterations):
        key = 'ASIC_SDK_HEALTH_EVENT_TABLE|' + strftime("%Y-%m-%d %H:%M:%S", gmtime(random() * 3000000000))
        state_db.hmset(state_db.STATE_DB, key, {'severity': severity, 'category': 'asic_hw'})
