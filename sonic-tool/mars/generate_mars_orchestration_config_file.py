"""
Run this script, and will help you to generate all the config used in the mars configuration for 201911, 202012,
develop branch
When there is new db added to the regression, need to update this file
How to run: python sonic-tool/mars/generate_mars_orchestration_config_file.py
"""
import os
# Here are the definition for the db files that should be used for every branch, every mars scenario.
# Community dbs in the develop branch

community_develop_set_1_dbs = [
    'pretest.db',
    'routes.db',
    'counters.db',
    'dhcp.db',
    'pfcwd.db',
    'layer2.db',
    'layer3.db',
    'common.db',
    'wjh.db',
    'fast_reboot.db',
    'warm_reboot.db',
    'span.db'
]

community_develop_rpc_dbs = [
    'pre_rpc.db',
    'rpc_qos.db',
    'rpc_pfc_asym_and_copp.db',
    'rpc_qos_dualtor.db',
    'post_rpc.db'
]

community_develop_set_2_dbs = [
    'pretest.db',
    'acl.db',
    'bfd.db',
    'radv.db',
    'ecmp.db',
    'ip_neigh.db',
    'resources.db',
    'tunnel.db',
    'generic_hash.db',
    'techsupport.db',
    'interfaces.db',
    'sub_port_interfaces.db',
    'system_health.db',
    'sflow.db',
    'bgp.db',
    'pbh.db',
    'generic_config_updater.db',
    'cold_reboot.db',
    'autorestart.db',
    'dualtor.db',
    'link.db',
    'upgrade_related.db'
]

community_develop_generic_dbs = [
    'system.db',
    'mgmtvrf.db',
]

community_develop_as_dbs = [
    'pretest.db',
    'acl.db',
    'routes.db',
    'dhcp.db',
    'pfcwd.db',
    'layer2.db',
    'layer3.db',
    'link.db',
    'span.db',
    'bfd.db',
    'radv.db',
    'ecmp.db',
    'ip_neigh.db',
    'resources.db',
    'tunnel.db',
    'generic_hash.db',
    'counters.db',
    'techsupport.db',
    'interfaces.db',
    'bgp.db',
    'autorestart.db',
    'sflow.db',
    'dualtor.db',
    'dualtor_io.db',
    'pre_rpc.db',
    'dualtor_dscp_remapping.db',
    'rpc_qos.db',
    'post_rpc.db'
]

community_develop_aa_dbs = [
    'pretest.db',
    'dualtor.db',
    'dualtor_io.db',
    'dualtor_aa_t0.db'
]

# Canonical dbs for develop branch
canonical_develop_dbs = [
    'canonical/pretest.db',
    'platform.db',
    'clock.db',
    'canonical/nightly.db',
    'canonical/push_gate_with_upgrade.db',
    'dynamic_buffer.db',
    'techsupport_any_topo.db',
    'platform_fwutil.db',
    'canonical/secure_boot.db'
]


community_keys = ["base_version", "target_version", "rpc_image", "custom_tarball_name", "target_version_specified",
                  "deploy_only_target", "skip_weekend_cases", "regression_type", "branch", "execution_block_generator"]

dualtor_as_keys = ["base_version", "rpc_image", "custom_tarball_name", "skip_weekend_cases", "regression_type",
                   "branch", "execution_block_generator"]

dualtor_aa_keys = ["topology", "base_version", "rpc_image", "custom_tarball_name", "skip_weekend_cases",
                   "regression_type", "branch", "execution_block_generator"]

canonical_keys = ["base_version", "custom_tarball_name", "send_takeover_notification",
                  "skip_weekend_cases", "regression_type", "branch", "execution_block_generator"]
canonical_upgrade_keys = ["base_version", "target_version"]


def print_configs(f, config_key_list, config_dict):
    f.write("{\n")
    last_key = config_key_list[-1]
    for config_key in config_key_list:
        if config_key == last_key:
            f.write("  \"{}\": \"{}\"".format(config_key, config_dict[config_key]))
        else:
            f.write("  \"{}\": \"{}\",".format(config_key, config_dict[config_key]))
        f.write("\n")
    f.write("}\n")


def gen_community_config(dbs):
    community_config = {
        "base_version": "/auto/sw_system_release/sonic/main_branch_verification_pointer-base.bin",
        "target_version": "/auto/sw_system_release/sonic/main_branch_verification_pointer.bin",
        "rpc_image": "/auto/sw_system_release/sonic/main_branch_verification_pointer-rpc.bin",
        "custom_tarball_name": "main_branch_verification_pointer.db.1.tgz",
        "target_version_specified": "yes",
        "deploy_only_target": "yes",
        "skip_weekend_cases": "yes",
        "regression_type": "regression",
        "branch": "master"
    }
    execution_block_generator = [
        {'entry_points': 'SONIC_MGMT', 'tests_dbs_tarball': 'sonic-mgmt/sonic-tool/mars/dbs/community/{}'.format(db)}
        for db in dbs]
    community_config["execution_block_generator"] = str(execution_block_generator)

    return community_config


def gen_dualtor_as_config(dbs):
    as_config = {
        "base_version": "/auto/sw_system_release/sonic/main_branch_verification_pointer.bin",
        "rpc_image": "/auto/sw_system_release/sonic/main_branch_verification_pointer-rpc.bin",
        "custom_tarball_name": "main_branch_verification_pointer.db.1.tgz",
        "skip_weekend_cases": "all",
        "regression_type": "regression",
        "branch": "master"
    }
    execution_block_generator = [
        {'entry_points': 'SONIC_MGMT', 'tests_dbs_tarball': 'sonic-mgmt/sonic-tool/mars/dbs/community/{}'.format(db)}
        for db in dbs]
    as_config["execution_block_generator"] = str(execution_block_generator)

    return as_config


def gen_dualtor_aa_config(dbs):
    aa_config = {
        "topology": "dualtor-aa",
        "base_version": "/auto/sw_system_release/sonic/main_branch_verification_pointer.bin",
        "rpc_image": "/auto/sw_system_release/sonic/main_branch_verification_pointer-rpc.bin",
        "custom_tarball_name": "main_branch_verification_pointer.db.1.tgz",
        "skip_weekend_cases": "all",
        "regression_type": "regression",
        "branch": "master"
    }
    execution_block_generator = [
        {'entry_points': 'SONIC_MGMT', 'tests_dbs_tarball': 'sonic-mgmt/sonic-tool/mars/dbs/community/{}'.format(db)}
        for db in dbs]
    aa_config["execution_block_generator"] = str(execution_block_generator)

    return aa_config


def gen_canonical_config(mars_branch, dbs, upgrade):
    caonical_config = {
        "base_version": f"/auto/sw_system_release/sonic/{mars_branch}_verification_pointer.bin",
        "custom_tarball_name": f"{mars_branch}_verification_pointer.db.1.tgz",
        "send_takeover_notification": "yes",
        "skip_weekend_cases": "yes",
        "regression_type": "regression",
        "branch": "master",
        "execution_block_generator": ""
    }
    if upgrade:
        caonical_config["target_version"] = caonical_config["base_version"]
        caonical_config["base_version"] = f"/auto/sw_system_release/sonic/{mars_branch}_verification_pointer-base.bin"

    execution_block_generator = []
    for db in dbs:
        if "canonical" in db:
            execution_block_generator.append({'entry_points': 'SONIC_MGMT',
                                              'tests_dbs_tarball': 'sonic-mgmt/sonic-tool/mars/dbs/{}'.format(db)})
        else:
            execution_block_generator.append({'entry_points': 'SONIC_MGMT',
                                              'tests_dbs_tarball': 'sonic-mgmt/sonic-tool/mars/dbs/community/{}'.format(
                                                  db)})
    caonical_config["execution_block_generator"] = str(execution_block_generator)
    return caonical_config


def print_community_configs(f, dbs):
    if dbs:
        mars_config_dict = gen_community_config(dbs)
        print_configs(f, community_keys, mars_config_dict)


def print_dualtor_as_configs(f, dbs):
    if dbs:
        mars_config_dict = gen_dualtor_as_config(dbs)
        print_configs(f, dualtor_as_keys, mars_config_dict)


def print_dualtor_aa_configs(f, dbs):
    if dbs:
        mars_config_dict = gen_dualtor_aa_config(dbs)
        print_configs(f, dualtor_aa_keys, mars_config_dict)


def print_cononical_configs(f, mars_branch, dbs, upgrade):
    mars_config_dict = gen_canonical_config(mars_branch, dbs, upgrade)
    if upgrade:
        print_configs(f, canonical_upgrade_keys, mars_config_dict)
    else:

        print_configs(f, canonical_keys, mars_config_dict)


def print_mars_configs(branch):
    path = os.path.dirname(os.path.abspath(__file__))
    file_name = f"mars_config_{branch}.txt"
    community_set_1_general_dbs = eval(f"community_{branch}_set_1_dbs") + eval(f"community_{branch}_rpc_dbs")
    community_set_2_general_dbs = eval(f"community_{branch}_set_2_dbs")
    if eval(f"community_{branch}_generic_dbs"):
        community_set_2_add_generic_dbs = eval(f"community_{branch}_set_1_dbs") + \
                                               eval(f"community_{branch}_generic_dbs")
    else:
        community_set_2_add_generic_dbs = None

    full_file_name = os.path.join(path, file_name)
    with open(full_file_name, 'w') as f:
        f.write("********************************Community**********************************************\n")
        f.write("#######################################################################################\n")
        f.write("#############################Notice here ##############################################\n")
        f.write("#############For weekend scenario,  Friday_Community_Regression_Set_1 #################\n")
        f.write("#############and Friday_Community_Regression_Set_2, need to update ####################\n")
        f.write("#############the value of skip_weekend_cases from 'yes' to 'no' #######################\n")
        f.write("#######################################################################################\n")
        f.write("++++++++++++++++++++++++++++++++Community_Regression_Set_1 start+++++++++++++++++++++++\n")
        f.write("################################general config#########################################\n")
        print_community_configs(f, community_set_1_general_dbs)
        f.write("++++++++++++++++++++++++++++++++Community_Regression_Set_1 end+++++++++++++++++++++++++\n")
        f.write("++++++++++++++++++++++++++++++++Community_Regression_Set_2 start+++++++++++++++++++++++\n")
        print_community_configs(f, community_set_2_general_dbs)
        f.write("################################full config############################################\n")
        if community_set_2_add_generic_dbs:
            f.write("################################ set_2_add_generic#####################################\n")
            f.write("########################## needed by r-leopard-72######################################\n")
            print_community_configs(f, community_set_2_add_generic_dbs)
        f.write("++++++++++++++++++++++++++++++++Community_Regression_Set_2 end+++++++++++++++++++++++++\n")
        f.write("***************************************************************************************\n")
        f.write("\n\n")

        f.write("*******************************Dualtor AS***********************************************\n")
        print_dualtor_as_configs(f, community_develop_as_dbs)
        f.write("\n\n")

        f.write("*******************************Dualtor AA***********************************************\n")
        print_dualtor_aa_configs(f, community_develop_aa_dbs)
        f.write("\n\n")

        f.write("*******************************Canonical***********************************************\n")
        canonical_dbs = eval(f"canonical_{branch}_dbs")

        f.write("++++++++++++++++++++++++++++++++ canonical_full_regression_main_branch ++++++++++++++++\n")
        print_cononical_configs(f, "main_branch", canonical_dbs, False)
        f.write("########## canonical upgrade related setups ########\n")
        f.write("## sonic_panther_r-panther-13, sonic_lionfish_r-lionfish-07, sonic_leopard_r-leopard-56##\n")
        print_cononical_configs(f, "main_branch", canonical_dbs, True)


if __name__ == "__main__":
    branch_list = ["develop"]
    for branch in branch_list:
        print_mars_configs(branch)
