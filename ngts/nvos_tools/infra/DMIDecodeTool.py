from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure
import logging

logger = logging.getLogger()


class DMIDecodeTool:
    def __init__(self, engines):
        self.engines = engines
        self.data = {}

    def _parse_output(self, output):
        current_handle = None
        for line in output.split('\n'):
            if line.startswith('Handle'):
                current_handle = line.split(',')[0].split()[-1]
                self.data[current_handle] = {'Type': line.split(',')[1].strip()}
            elif current_handle and ':' in line:
                key, value = line.split(':', 1)
                self.data[current_handle][key.strip()] = value.strip()

    def collect_dmi_info(self, *types):
        cmd = f"sudo dmidecode {' '.join([f'-t{t}' for t in types])}"
        output = self.engines.dut.run_cmd(cmd)
        self._parse_output(output)

    def collect_memory_info(self):
        """Collect memory information including configured memory speed"""
        cmd = "sudo dmidecode -t memory"
        output = self.engines.dut.run_cmd(cmd)
        self._parse_output(output)

    def get_memory_speed(self):
        """Extract configured memory speed from collected data and return as integer"""
        memory_speeds = []

        # Loop through all handles to find Configured Memory Speed
        for handle, info in self.data.items():
            configured_speed = info.get('Configured Memory Speed')
            if configured_speed:
                logger.info(f"Found Configured Memory Speed in {handle}: {configured_speed}")
                try:
                    # Extract numeric value from string like "2400 MT/s"
                    speed_str = configured_speed.strip().split()[0]
                    speed_int = int(speed_str)
                    memory_speeds.append(speed_int)
                    logger.info(f"Extracted memory speed from {handle}: {speed_int} MT/s")
                except (ValueError, IndexError):
                    logger.info(f"Failed to parse memory speed from {handle}: {configured_speed}")

        if not memory_speeds:
            logger.info("No Configured Memory Speed found in any handle")
            return None

        # Check if all memory speeds are the same
        if len(set(memory_speeds)) > 1:
            logger.info(f"Memory speed mismatch across handles: {memory_speeds}")
            return None

        logger.info(f"All handles show consistent memory speed: {memory_speeds[0]} MT/s")
        return memory_speeds[0]

    def validate_dmi_info(self):
        invalid_entries = []

        validation_rules = {
            '0x0000': ['Release Date', 'Vendor', 'Address', 'Version'],
            '0x0001': ['Serial Number', 'Product Name', 'Version', 'Manufacturer', 'SKU Number'],
            '0x0002': ['Product Name', 'Serial Number', 'Version', 'Manufacturer', 'Type'],
            '0x0003': ['Serial Number', 'Version', 'SKU Number', 'Manufacturer']
        }

        for handle, required_fields in validation_rules.items():
            if handle in self.data:
                for field in required_fields:
                    if field not in self.data[handle] or not self.data[handle][field]:
                        invalid_entries.append(f"{handle} - Missing or empty: {field}")
            else:
                invalid_entries.append(f"Handle {handle} not found")

        return invalid_entries

    def get_handle_info(self, handle):
        return self.data.get(handle, {})

    def get_all_dmi_info(self):
        return self.data

    @staticmethod
    def verify_dmi_info(engines, devices):
        """
        Verify DMI information using dmidecode
        """
        platform_info = OutputParsingTool.parse_json_str_to_dictionary(
            Platform().show()).get_returned_value()
        product_name = platform_info[PlatformConsts.SYSTEM_TYPE]

        with allure.step("Verify DMI information"):
            dmi_tool = DMIDecodeTool(engines)
            dmi_tool.collect_dmi_info(0, 1, 2, 3)  # Collect info for BIOS, System, Base Board, and Chassis

            errors = []

            # Define expected values
            expected_values = {
                '0x0000': {
                    'Vendor': "American Megatrends Inc.",
                    'Version': "5.13"
                },
                '0x0001': {
                    'Manufacturer': "Nvidia",
                    'Product Name': product_name,
                },
                '0x0002': {
                    'Manufacturer': "Nvidia",
                    'Type': "Motherboard"
                },
                '0x0003': {
                    'Manufacturer': "Nvidia",
                    'SKU Number': product_name
                }
            }

            for handle, expected in expected_values.items():
                with allure.step(f"Checking handle {handle}"):
                    info = dmi_tool.get_handle_info(handle)
                    for key, value in expected.items():
                        if info.get(key) != value:
                            errors.append(f"{handle} - {key} mismatch: Expected '{value}', Got '{info.get(key)}'")

            validation_errors = dmi_tool.validate_dmi_info()
            errors.extend(validation_errors)

            # Verify memory speed
            with allure.step("Verify memory speed"):
                dmi_tool.collect_memory_info()
                actual_memory_speed = dmi_tool.get_memory_speed()

                if actual_memory_speed is not None:
                    expected_memory_speed = devices.dut.memory_speed
                    if actual_memory_speed != expected_memory_speed:
                        errors.append(f"Memory speed mismatch: Expected {expected_memory_speed} MT/s, Got {actual_memory_speed} MT/s")
                elif actual_memory_speed is None:
                    errors.append("Memory speed information not found in DMI data")

            assert not errors, f"{len(errors)} DMI information mismatches or validation errors found:\n" + '\n'.join(
                errors)
