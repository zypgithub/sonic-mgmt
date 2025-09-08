"""
Constants for NMX simulator tests
"""

from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts

# Partition update timing constants
PARTITION_UPDATE_WAIT_TIME = 2  # seconds to wait for partition updates
PARTITION_OPERATION_WAIT_TIME = 10  # seconds to wait for partition operations

# Partition operation messages
PARTITION_UPDATE_WAIT_MESSAGE = "Wait for {} seconds until partitions are updated"
PARTITION_OPERATION_WAIT_MESSAGE = "Sleeping for {} seconds"

# Invalid mcast limit for testing (exceeds the maximum allowed value)
MAX_MCAST_LIMIT = 1024
INVALID_MCAST_LIMIT = MAX_MCAST_LIMIT + 1

# Error messages for invalid mcast limit
INVALID_MCAST_NVUE_ERROR = f"Valid range for mcast-limit is 0 - {MAX_MCAST_LIMIT}"
INVALID_MCAST_OPENAPI_ERROR = "{{}} is greater than the maximum of {}".format(MAX_MCAST_LIMIT)
