import logging
import random
import pytest
import time
import re
import copy

from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Sdn import Sdn
from ngts.nvos_constants.constants_nvos import PlatformConsts, IbConsts, ApiType, OutputFormat, SystemConsts, ClusterAppsLogLevels, NvosConst, ImageConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools, disabled_access_ports
from ngts.tests_nvos.general.security.tpm_attestation.helpers import factory_reset_tpm_checker
from ngts.tests_nvos.system.gnmi.helpers import factory_reset_gnmi_checker
from ngts.tests_nvos.system.factory_reset.helpers import add_verification_data, \
    verify_cleanup_done, verify_the_setup_is_functional, get_current_time
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts

logger = logging.getLogger()
EMPTY_PARTITION_ID = 10
EMPTY_PARTITION_NAME = "empty_partition"
MIN_MCAST = 0
MAX_MCAST = 1024
# @disabled_access_ports


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cluster_partition(engines, devices, test_api, has_loopbox):

    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    with allure.step("Create Cluster object"):
        cluster = Cluster()
        sdn = Sdn()

        used_partition_ids = []
        used_locations_uuids = []
        partition_mapping_to_location_uuid = {}
        partition_mapping_to_location_uuid_copy = {}
        partitions = {}
        all_location_ids_uuids = []
        partition_ids = []
    try:
        with allure.step("Enable cluster"):
            ClusterTools().start_cluster(cluster, output_format)

        with allure.step("Show All Partitions"):
            output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                 output_format=output_format).get_returned_value()
            partition_ids = output.keys()
        with allure.step("Show partition per partition id"):
            for partition_id in partition_ids:
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[partition_id].show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
        with allure.step("Create empty partition"):
            resiliency_mode = random.choice(ClusterConsts.RESILIENCY_MODES)
            mcast_limit = random.randint(MIN_MCAST, MAX_MCAST)
            sdn.partition.partition_id[EMPTY_PARTITION_ID].action_create_partition_id(name=EMPTY_PARTITION_NAME, resiliency_mode=resiliency_mode, mcast_limit=mcast_limit)

            with allure.step("Checking newly created partition"):
                assert EMPTY_PARTITION_ID in output.keys(), f'Partition {EMPTY_PARTITION_ID} was not created'
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[EMPTY_PARTITION_ID].show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # Add a method to verify all attributes --- {'health': '', 'locations': {}, 'mcast-limit': 0, 'name': '', 'num-gpus': 0, 'partition-type': '', 'resiliency-mode': '', 'uuids': {}}

        with allure.step("Delete empty partition"):
            sdn.partition.partition_id[EMPTY_PARTITION_ID].action_delete_partition()
            output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                 output_format=output_format).get_returned_value()
            assert EMPTY_PARTITION_ID not in output.keys(), f'Partition {EMPTY_PARTITION_ID} was not deleted'

            # Todo - Add assert for initial expected state.
            # Todo - Save all "location_ids" and "uuids"
            partitions = []
            # TODO - used_partition_ids Needs to be adjusted with initial partitions!
        with allure.step("Show Partition with partition id parameter"):
            pass
            # Todo - Once we have output, fetch all partitions (1) - part_id, need to check if there is multiple.
            for part_id in partitions:
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[part_id].show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # Here, we can create a mapping between uuid and location ID! key is partition, value is list of tuples, uuid and loc id
                list_of_gpus = []  # You can see it from HLD.
                for gpu in list_of_gpus:
                    location_id = ''  # TODO - Extract from output
                    uuid = ''  # TODO - Extract from output
                    partition_mapping_to_location_uuid[part_id].append((location_id, uuid))
                    partition_mapping_to_location_uuid_copy = copy.deepcopy(partition_mapping_to_location_uuid)
                    all_location_ids_uuids = []  # Will contain tuples.
                    location_ids = []  # After we have real output, extract form output
                    uuids = []  # After we have real output, extract form output

        with allure.step("Create and validate a new partition"):
            partition_id = random.choice([x for x in range(100, 201) if x not in used_partition_ids])
            used_partition_ids.append(partition_id)
            resiliency_mode = random.choice(ClusterConsts.RESILIENCY_MODES)
            confidential_compute = random.choice(ClusterConsts.CONFIDENTIAL_COMPUTE)
            mcast_limit = random.randint(100, 1000)  # TODO - check with chris, what is the expected range of values here? And what is the usage of this param?
            created_partition_id, location_id_uuid, gpu_taken_from_partition, create_output = \
                create_and_validate_partition(used_partition_ids, sdn, used_locations_uuids,
                                              partition_mapping_to_location_uuid, output_format,
                                              partition_id=partition_id, resiliency_mode=resiliency_mode,
                                              confidential_compute=confidential_compute, mcast_limit=mcast_limit)
            with allure.step("Validate partition is created"):
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # Todo - validate output.
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[partition_id].show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # Todo - validate output.

        with allure.step("Update existing partition"):
            add_mode = random.choice(['uuid', 'location-id'])
            location_id_uuid, partition_to_take_gpu_from = choose_gpu_to_move_from_partition(partition_mapping_to_location_uuid, used_locations_uuids)
            used_locations_uuids.append(location_id_uuid)
            if add_mode == 'uuid':
                sdn.partition.partition_id[created_partition_id].uuid.uuid_value[param_value].action_update_partition()
            else:
                sdn.partition.partition_id[created_partition_id].location.location_id[param_value].action_update_partition()

            update_partition_to_location_uuid_map(partition_id, created_partition_id, location_id_uuid, partition_to_take_gpu_from, partition_mapping_to_location_uuid)

            with allure.step("Validate partition is created"):
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # Todo - validate output.
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[partition_id].show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # Todo - validate output.

        with allure.step("Create and validate a second partition"):
            partition_id = random.choice([x for x in range(100, 201) if x not in used_partition_ids])
            used_partition_ids.append(partition_id)
            resiliency_mode = random.choice(ClusterConsts.RESILIENCY_MODES)
            confidential_compute = random.choice(ClusterConsts.CONFIDENTIAL_COMPUTE)
            mcast_limit = random.randint(100, 1000)  # TODO - check with chris, what is the expected range of values here? And what is the usage of this param?
            second_created_partition_id, second_location_id_uuid, second_gpu_taken_from_partition, create_output = \
                create_and_validate_partition(used_partition_ids, sdn, used_locations_uuids, partition_mapping_to_location_uuid,
                                              output_format, partition_id=partition_id, resiliency_mode=resiliency_mode,
                                              confidential_compute=confidential_compute, mcast_limit=mcast_limit)
            with allure.step("Validate partition is created"):
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # Todo - validate output.
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[second_created_partition_id].show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # Todo - validate output.

        # sdn.partition.partition_id[partition_id].action_create_partition_id(ClusterConsts.PARTITIONS_NAMES[0], resiliency_mode, confidential_compute, mcast_limit, uuid=param_value)

        with allure.step("Use ansible to verify connectivity between two gpus on same partition"):
            pass

        with allure.step("Use ansible to verify no connectivity between two gpus on different partition"):
            pass

        with allure.step("restore sdn partition - which removes a GPU from partition"):
            location_id_uuid, partition_to_take_gpu_from = choose_gpu_to_move_from_partition(partition_mapping_to_location_uuid, used_locations_uuids)
            if add_mode == 'uuid':
                sdn.partition.partition_id[created_partition_id].uuid.uuid_value[param_value].action_restore_partition()
            else:
                sdn.partition.partition_id[created_partition_id].location.location_id[param_value].action_restore_partition()

            output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[partition_to_take_gpu_from].show(output_format=output_format),
                                                                 output_format=output_format).get_returned_value()

            if location_id_uuid in used_locations_uuids:
                used_locations_uuids.remove(location_id_uuid)

            update_partition_to_location_uuid_map(ClusterConsts.DEFAULT_PARTITION, ClusterConsts.DEFAULT_PARTITION, location_id_uuid, partition_to_take_gpu_from, partition_mapping_to_location_uuid)

        with allure.step("Delete created partitions"):
            # TODO Show second partition, and save all uuids/locations we have there, and remove them from used location uuid list.
            # TODO Then after deleting, update partition_mapping_to_location_uuid, deleted partition will be removed, and default one will get all its components.
            sdn.partition.partition_id[second_created_partition_id].action_delete_partition()
            used_partition_ids.remove(second_created_partition_id)
            with allure.step("Show All Partitions"):
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # TODO -  Make sure partition is indeed deleted.
            sdn.partition.partition_id[created_partition_id].action_delete_partition()
            with allure.step("Show All Partitions"):
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # TODO -  Make sure partition is indeed deleted.

            # TODO - Validate being back at initial state.

    finally:
        with allure.step('Restore to initial state - delete all partitions Except for default partition'):
            partitions = partition_mapping_to_location_uuid.keys()
            for partition in partitions:
                if partition != ClusterConsts.DEFAULT_PARTITION:
                    sdn.partition.partition_id[partition].action_delete_partition()


@disabled_access_ports
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cluster_partition_bad_flow(engines, devices, test_api, has_loopbox):

    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    with allure.step("Create Cluster object"):
        cluster = Cluster()
        sdn = Sdn()

        used_partition_ids = []
        used_locations_uuids = []
        partition_mapping_to_location_uuid = {}
        partition_mapping_to_location_uuid_copy = {}
        partitions = {}
        all_location_ids_uuids = []

    try:
        with allure.step("Enable cluster"):
            ClusterTools().start_cluster(cluster, output_format)

        with allure.step("Show All Partitions"):
            output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                 output_format=output_format).get_returned_value()
            # Todo - Add assert for initial expected state.
            # Todo - Save all "location_ids" and "uuids"
            partitions = []
            # TODO - used_partition_ids Needs to be adjusted with initial partitions!
        with allure.step("Show Partition with partition id parameter"):
            pass
            # Todo - Once we have output, fetch all partitions (1) - part_id, need to check if there is multiple.
            for part_id in partitions:
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[part_id].show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # Here, we can create a mapping between uuid and location ID! key is partition, value is list of tuples, uuid and loc id
                list_of_gpus = []  # You can see it from HLD.
                for gpu in list_of_gpus:
                    location_id = ''  # TODO - Extract from output
                    uuid = ''  # TODO - Extract from output
                    partition_mapping_to_location_uuid[part_id].append((location_id, uuid))
                    partition_mapping_to_location_uuid_copy = copy.deepcopy(partition_mapping_to_location_uuid)
                    location_ids = []  # After we have real output, extract form output
                    uuids = []  # After we have real output, extract form output
                    all_location_ids_uuids = []  # Fill here

        with allure.step("Create and validate a new partition"):
            partition_id = random.choice([x for x in range(100, 201) if x not in used_partition_ids])
            used_partition_ids.append(partition_id)
            resiliency_mode = random.choice(ClusterConsts.RESILIENCY_MODES)
            confidential_compute = random.choice(ClusterConsts.CONFIDENTIAL_COMPUTE)
            mcast_limit = random.randint(100, 1000)  # TODO - check with chris, what is the expected range of values here? And what is the usage of this param?
            created_partition_id, location_id_uuid, gpu_taken_from_partition, create_output = \
                create_and_validate_partition(used_partition_ids, sdn, used_locations_uuids,
                                              partition_mapping_to_location_uuid, output_format,
                                              partition_id=partition_id, resiliency_mode=resiliency_mode,
                                              confidential_compute=confidential_compute, mcast_limit=mcast_limit)
            with allure.step("Validate partition is created"):
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # Todo - validate output.
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[partition_id].show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # Todo - validate output.

            with allure.step("Re-Create the exact same partitions and parameters, expected to get proper error message"):
                add_mode = random.choice(['location-id', 'uuid'])
                if add_mode == 'uuid':
                    pass  # Dont have current format for uuid in order to generate a non real one.
                    create_output = sdn.partition.partition_id[partition_id].action_create_partition_id(ClusterConsts.PARTITIONS_NAMES[0], resiliency_mode, confidential_compute, mcast_limit, uuid=location_id_uuid[1])
                else:
                    create_output = sdn.partition.partition_id[partition_id].action_create_partition_id(ClusterConsts.PARTITIONS_NAMES[0], resiliency_mode, confidential_compute, mcast_limit, location=location_id_uuid[0])

                # TODO Validate correct error message

                with allure.step("Validate partition is created"):
                    output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                         output_format=output_format).get_returned_value()
                    # Todo - validate output. nothing is changed
                    output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[created_partition_id].show(output_format=output_format),
                                                                         output_format=output_format).get_returned_value()
                    # Todo - validate output. nothing is changed

            with allure.step("Re-Create same partitions with different parameters"):
                resiliency_mode = random.choice(ClusterConsts.RESILIENCY_MODES)
                confidential_compute = random.choice(ClusterConsts.CONFIDENTIAL_COMPUTE)
                mcast_limit = random.randint(100, 1000)  # TODO - check with chris, what is the expected range of values here? And what is the usage of this param?
                add_mode = random.choice(['location-id', 'uuid'])
                if add_mode == 'uuid':
                    pass  # Dont have current format for uuid in order to generate a non real one.
                    create_output = sdn.partition.partition_id[partition_id].action_create_partition_id(ClusterConsts.PARTITIONS_NAMES[0], resiliency_mode, confidential_compute, mcast_limit, uuid=location_id_uuid[1])
                else:
                    create_output = sdn.partition.partition_id[partition_id].action_create_partition_id(ClusterConsts.PARTITIONS_NAMES[0], resiliency_mode, confidential_compute, mcast_limit, location=location_id_uuid[0])

                # TODO - Check that parameters of the already existing partition is being updated.

                with allure.step("Validate partition is created"):
                    output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                         output_format=output_format).get_returned_value()
                    # Todo - validate output.
                    output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[created_partition_id].show(output_format=output_format),
                                                                         output_format=output_format).get_returned_value()
                    # Todo - validate output.

            with allure.step("Create Partition with undefined parameters"):
                parameters = ['resiliency_mode', 'confidential_compute', 'mcast_limit']
                undefined_params = random.sample(parameters, random.randint(0, len(parameters)))
                resiliency_mode = random.choice(ClusterConsts.RESILIENCY_MODES) if 'resiliency_mode' not in undefined_params else 'undefined'
                confidential_compute = random.choice(ClusterConsts.CONFIDENTIAL_COMPUTE) if 'confidential_compute' not in undefined_params else 'undefined'
                mcast_limit = random.randint(100, 1000) if 'mcast_limit' not in undefined_params else 'undefined'
                add_mode = random.choice(['location-id', 'uuid'])
                if add_mode == 'uuid':
                    pass  # Dont have current format for uuid in order to generate a non real one.
                    create_output = sdn.partition.partition_id[partition_id].action_create_partition_id(ClusterConsts.PARTITIONS_NAMES[0], resiliency_mode, confidential_compute, mcast_limit, uuid=location_id_uuid[1])
                else:
                    create_output = sdn.partition.partition_id[partition_id].action_create_partition_id(ClusterConsts.PARTITIONS_NAMES[0], resiliency_mode, confidential_compute, mcast_limit, location=random_location_id)
                    # Todo - Validate we get a proper fail message.
                # TODO - Check that we get a proper fail message.
                with allure.step("Validate partition is not created"):
                    output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                         output_format=output_format).get_returned_value()
                    # Todo - validate output.
                    output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[created_partition_id].show(output_format=output_format),
                                                                         output_format=output_format).get_returned_value()
                    # Todo - validate output.

            # all_location_ids_uuids
            with allure.step("Create partition with non-existing location_id"):
                # Extract location_ids from location_ids_uuids
                location_ids = [item[0] for item in all_location_ids_uuids]

                # Generate a random location_id that is not in location_ids
                random_location_id = generate_random_id()
                while random_location_id in location_ids:
                    random_location_id = generate_random_id()

                partition_id = random.choice([x for x in range(100, 201) if x not in used_partition_ids])
                used_partition_ids.append(partition_id)
                resiliency_mode = random.choice(ClusterConsts.RESILIENCY_MODES)
                confidential_compute = random.choice(ClusterConsts.CONFIDENTIAL_COMPUTE)
                mcast_limit = random.randint(100, 1000)  # TODO - check with chris, what is the expected range of values here? And what is the usage of this param?
                add_mode = random.choice(['location-id', 'uuid'])
                if add_mode == 'uuid':
                    pass  # Dont have current format for uuid in order to generate a non real one.
                    # create_output = sdn.partition.partition_id[partition_id].action_create_partition_id(ClusterConsts.PARTITIONS_NAMES[0], resiliency_mode, confidential_compute, mcast_limit, uuid=location_id_uuid[1])
                else:
                    create_output = sdn.partition.partition_id[partition_id].action_create_partition_id(ClusterConsts.PARTITIONS_NAMES[0], resiliency_mode, confidential_compute, mcast_limit, location=random_location_id)
                    # Todo - Validate we get a proper fail message.

                with allure.step("Restore non existing partition"):
                    add_mode = random.choice(['location-id', 'uuid'])
                    if add_mode == 'uuid':
                        pass  # Dont have current format for uuid in order to generate a non real one.
                        sdn.partition.partition_id[partition_id].uuid.uuid_value[location_id_uuid[1]].action_restore_partition()
                    else:
                        sdn.partition.partition_id[partition_id].location.location_id[random_location_id].action_restore_partition()
                    # Todo - Validate we get a proper fail message.

                with allure.step("Delete non existing partition"):
                    output = sdn.partition.partition_id[partition_id].action_delete_partition()
                    # Todo - Make sure to get proper failure message.

        with allure.step("Update existing partition"):
            add_mode = random.choice(['uuid', 'location-id'])
            # used_locations_uuids[add_mode].append(param_value)
            location_id_uuid, partition_to_take_gpu_from = choose_gpu_to_move_from_partition(partition_mapping_to_location_uuid, used_locations_uuids)
            # used_locations_uuids.append(location_id_uuid)
            if add_mode == 'uuid':
                sdn.partition.partition_id[created_partition_id].uuid.uuid_value[location_id_uuid[1]].action_update_partition()
            else:
                sdn.partition.partition_id[created_partition_id].location.location_id[location_id_uuid[0]].action_update_partition()

            update_partition_to_location_uuid_map(partition_id, created_partition_id, location_id_uuid, partition_to_take_gpu_from, partition_mapping_to_location_uuid)

            with allure.step("Validate partition is created"):
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # Todo - validate output.
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[partition_id].show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                # Todo - validate output.

        with allure.step("Update existing partition with same GPU from previous step - Expected to fail"):
            add_mode = random.choice(['uuid', 'location-id'])
            # used_locations_uuids[add_mode].append(param_value)
            # used_locations_uuids.append(location_id_uuid)
            if add_mode == 'uuid':
                sdn.partition.partition_id[created_partition_id].uuid.uuid_value[location_id_uuid[1]].action_update_partition()
            else:
                sdn.partition.partition_id[created_partition_id].location.location_id[location_id_uuid[0]].action_update_partition()
            # Todo - Validate we get error msg, and its not added again (Verify show partition [part_id] output is still the same as in prev step.

        with allure.step("Try to add A GPU to a non-existing partition"):
            partitions = partition_mapping_to_location_uuid.keys()
            non_existing_partition = random.randint(1, 200)
            while random_number in partitions:
                non_existing_partition = random.randint(1, 200)
            add_mode = random.choice(['uuid', 'location-id'])
            # used_locations_uuids[add_mode].append(param_value)
            used_locations_uuids.append(location_id_uuid)
            if add_mode == 'uuid':
                sdn.partition.partition_id[non_existing_partition].uuid.uuid_value[location_id_uuid[1]].action_update_partition()
            else:
                sdn.partition.partition_id[non_existing_partition].location.location_id[location_id_uuid[0]].action_update_partition()
            # Todo - Validate we get error msg, and its not added again (Verify show partition [part_id] output is still the same as in prev step.

        with allure.step("Restore non existing partition"):
            add_mode = random.choice(['location-id', 'uuid'])
            if add_mode == 'uuid':
                sdn.partition.partition_id[non_existing_partition].uuid.uuid_value[location_id_uuid[1]].action_restore_partition()
            else:
                sdn.partition.partition_id[non_existing_partition].location.location_id[location_id_uuid[0]].action_restore_partition()

    finally:
        with allure.step('Restore to initial state - delete all partitions Except for default partition'):
            partitions = partition_mapping_to_location_uuid.keys()
            for partition in partitions:
                if partition != ClusterConsts.DEFAULT_PARTITION:
                    sdn.partition.partition_id[partition].action_delete_partition()


def update_partition_to_location_uuid_map(partition_id, created_partition_id, location_id_uuid, partition_to_take_gpu_from, partition_mapping_to_location_uuid):
    if partition_id not in partition_mapping_to_location_uuid.keys():
        partition_mapping_to_location_uuid[partition_id] = []
    partition_mapping_to_location_uuid[created_partition_id].append(location_id_uuid)
    partition_mapping_to_location_uuid[partition_to_take_gpu_from].remove(location_id_uuid)
    if partition_mapping_to_location_uuid[partition_to_take_gpu_from] == []:
        del partition_mapping_to_location_uuid[partition_to_take_gpu_from]


def generate_random_id():
    return f"{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"


def create_and_validate_partition(used_partition_ids, sdn, used_locations_uuids, partition_mapping_to_location_uuid,
                                  output_format, location_id_uuid='', gpu_taken_from_partition='', partition_id='', resiliency_mode='',
                                  confidential_compute='', mcast_limit=''):
    with allure.step("Randomly Choose whether to create partition using uuid or location-id and randomize other parameters"):
        # nv action create sdn partition 1 name part1 resiliency-mode FULL_BANDWIDTH confidential-compute true mcast-limit 10 location-id 1.1.1.1
        add_mode = random.choice(['location-id', 'uuid'])
        if location_id_uuid == '' or gpu_taken_from_partition == '':
            location_id_uuid, gpu_taken_from_partition = choose_gpu_to_move_from_partition(partition_mapping_to_location_uuid, used_locations_uuids)
        used_locations_uuids.append(location_id_uuid)
    if add_mode == 'uuid':
        create_output = sdn.partition.partition_id[partition_id].action_create_partition_id(ClusterConsts.PARTITIONS_NAMES[0], resiliency_mode, confidential_compute, mcast_limit, uuid=location_id_uuid[1])
    else:
        create_output = sdn.partition.partition_id[partition_id].action_create_partition_id(ClusterConsts.PARTITIONS_NAMES[0], resiliency_mode, confidential_compute, mcast_limit, location=location_id_uuid[0])

        if partition_id not in partition_mapping_to_location_uuid.keys():
            partition_mapping_to_location_uuid[partition_id] = []
        partition_mapping_to_location_uuid[partition_id].append(location_id_uuid)
        partition_mapping_to_location_uuid[gpu_taken_from_partition].remove(location_id_uuid)
        if partition_mapping_to_location_uuid[gpu_taken_from_partition] == []:
            del partition_mapping_to_location_uuid[gpu_taken_from_partition]
            used_partition_ids.remove(gpu_taken_from_partition)

    # Returns, new created partition id, GPU that was added to partition (uuid /loc_id), And what is the partition GPU was taken from.
    return partition_id, location_id_uuid, gpu_taken_from_partition, create_output


def choose_gpu_to_move_from_partition(partition_mapping_to_location_uuid, used_locations_uuids):
    # used_location_uuids - Contains GPUs that have been already moved.
    # If you want to allow choosing again, you can move an empty used_locations_uuids list.
    retries = 10
    partition_to_take_gpu_from = random.choice(list(partition_mapping_to_location_uuid.keys()))

    while retries > 0:
        available_locations_uuids = [k for k in partition_mapping_to_location_uuid[partition_to_take_gpu_from] if k not in used_locations_uuids]
        if available_locations_uuids:
            location_id_uuid = random.choice(available_locations_uuids)
            break
        else:
            partition_to_take_gpu_from = random.choice(list(partition_mapping_to_location_uuid.keys()))
        retries -= 1
    if retries == 0:
        raise ValueError("Failed to obtain a valid add_mode or param_value - No more additional GPUs")

    return location_id_uuid, partition_to_take_gpu_from
