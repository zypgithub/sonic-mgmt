
import os
import subprocess
SCRIPT_PATH = "./ngts/scripts/air_spin/air_spin.sh"


def test_invalid_setup_name():
    name = "invalid-setup-name"
    invalid_add_chars = ["[]", "*", "!", "_", ":", "%", "^", "&", "(", ")", "+", "=", "~", "|", "\\", "/", "?", "<", ">", "{", "}", "[", "]"]
    for add_char in invalid_add_chars:
        invalid_setup_name = name + add_char + "test"
        print(f"Testing invalid setup name: {invalid_setup_name}")
        cmd = f'{SCRIPT_PATH} create --setup_name \"{invalid_setup_name}\"\
            --topology_type canonical --base_version \"/auto/sw_system_release/sonic/master_SPC6-latest-internal-sonic-mellanox.bin\"\
            --topology \"ptf-any\" --custom_tarball_name \"SONIC_CANONICAL-sonic-mgmt_develop.db.1.tgz\" --branch \"develop\" --dut_name \"new_test_dut\"\
            --dut_hwsku \"ACS-SN6600\" --chip_type \"SPC6\" --custom_links_path \"/auto/mtrsysgwork/ytzur/link.json\" --dbs_to_run \"/auto/mtrsysgwork/ytzur/db.json\"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        assert result.returncode != 0
        assert "Error: Setup name must contain only letters, numbers, and hyphens(-):" in result.stdout, print(result.stdout)
        print(f"Test invalid setup name: {invalid_setup_name} passed")


def required_params_test():
    required_params = ["--topology_type", "--base_version", "--topology", "--custom_tarball_name", "--branch", "--dut_hwsku"]
    for param in required_params:
        cmd = f'{SCRIPT_PATH} create --setup_name \"test\" --topology_type \"canonical\" --base_version \"/auto/sw_system_release/sonic/master_SPC6-latest-internal-sonic-mellanox.bin\" --topology \"ptf-any\" --custom_tarball_name \"SONIC_CANONICAL-sonic-mgmt_develop.db.1.tgz\" --branch \"develop\" --dut_name \"new_test_dut\" --dut_hwsku \"ACS-SN6600\" --chip_type \"SPC6\" --custom_links_path \"/auto/mtrsysgwork/ytzur/link.json\" --dbs_to_run \"/auto/mtrsysgwork/ytzur/db.json\"'
        cmd = cmd.replace(param, "")
        print("removing param: ", param)
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(result.stderr)
        assert result.returncode != 0, print(result.stdout)
        print(f"Test required param: {param} passed\n\n")


def test_valid_case():
    cmd = f'{SCRIPT_PATH} create --setup_name \"dynamic-setup\" --topology_type \"canonical\" --base_version \"/auto/sw_system_release/sonic/master_SPC6-latest-internal-sonic-mellanox.bin\" --topology \"ptf-any\" --custom_tarball_name \"SONIC_CANONICAL-sonic-mgmt_develop.db.1.tgz\" --branch \"develop\" --dut_name \"new_test_dut\" --dut_hwsku \"ACS-SN6600\" --chip_type \"SPC6\" --custom_links_path \"/auto/mtrsysgwork/ytzur/link.json\" --dbs_to_run \"/auto/mtrsysgwork/ytzur/db.json\"'


if __name__ == "__main__":
    # test_invalid_setup_name()
    required_params_test()
