from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure


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

            # Perform validation
            validation_errors = dmi_tool.validate_dmi_info()
            errors.extend(validation_errors)

            assert not errors, f"{len(errors)} DMI information mismatches or validation errors found:\n" + '\n'.join(
                errors)
