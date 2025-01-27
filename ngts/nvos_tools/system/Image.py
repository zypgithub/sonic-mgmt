import logging

from ngts.nvos_constants.constants_nvos import ApiType, ActionConsts, ActionParamConsts
from ngts.nvos_constants.constants_nvos import ImageConsts
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.Files import Files
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class Image(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/image')
        self.files = Files(self)

    def unset(self, op_param=""):
        raise Exception("unset is not implemented for /image")

    def action_uninstall(self, params="", expected_str="", engine=None, verify_res: bool = True):
        with allure.step("Uninstall {params} system image".format(params=params)):
            if not engine:
                engine = TestToolkit.engines.dut
            res: ResultObj = SendCommandTool.execute_command_expected_str(self.api_obj[TestToolkit.tested_api].action_image,
                                                                          expected_str, engine,
                                                                          ActionConsts.UNINSTALL, self.get_resource_path(),
                                                                          params)
            if verify_res:
                return res.get_returned_value()
            else:
                res.ignore_result()
                return res.returned_value

    def action_boot_next(self, partition_id, expected_str=''):
        with allure.step(f"Set image '{partition_id}' to boot next"):
            return self.action(ActionConsts.BOOT_NEXT, (ImageConsts.PARTITION, partition_id),
                               expected_output=expected_str)

    def get_image_field_value(self, field_name):
        output = OutputParsingTool.parse_json_str_to_dictionary(BaseComponent.show(self)).get_returned_value()
        if field_name in output.keys():
            return output[field_name]
        return None

    def get_image_field_values(self, field_names=[ImageConsts.NEXT_IMG, ImageConsts.CURRENT_IMG, ImageConsts.PARTITION1_IMG,
                                                  ImageConsts.PARTITION2_IMG]):
        output = OutputParsingTool.parse_json_str_to_dictionary(BaseComponent.show(self)).get_returned_value()
        values = {}
        for field_name in field_names:
            if field_name in output.keys():
                values[field_name] = output[field_name]
            else:
                values[field_name] = ""
        return values

    def get_image_partition(self, image_name, images_dictionary={}):
        images_dictionary = images_dictionary if images_dictionary else self.get_image_field_values()
        partition = None
        if image_name == images_dictionary[ImageConsts.PARTITION1_IMG][ImageConsts.BUILD_ID]:
            partition = ImageConsts.PARTITION1_IMG
        elif image_name == images_dictionary[ImageConsts.PARTITION2_IMG][ImageConsts.BUILD_ID]:
            partition = ImageConsts.PARTITION2_IMG
        return partition

    def boot_next_and_verify(self, partition_id):
        self.action_boot_next(partition_id)
        images = self.get_image_field_values()
        res_obj = ValidationTool.verify_expected_output(self.show(), ImageConsts.BUILD_ID)
        res_obj.ignore_result()
        if res_obj.result:  # solution for previous show system image output
            with allure.step("Verifying the boot next image updated successfully"):
                if partition_id == ImageConsts.PARTITION1_IMG:
                    assert images[ImageConsts.NEXT_IMG] == '1', "Failed to set the new image to boot next"
                elif partition_id == ImageConsts.PARTITION2_IMG:
                    assert images[ImageConsts.NEXT_IMG] == '2', "Failed to set the new image to boot next"
                else:
                    raise ValueError(f"Invalid partition_id: {partition_id}")
        else:
            with allure.step("Verifying the boot next image updated successfully"):
                assert images[ImageConsts.NEXT_IMG] == images[partition_id], "Failed to set the new image to boot next"

    def verify_show_images_output(self, expected_keys_values):
        with allure.step("verify expected values"):
            output = self.get_image_field_values()
            for field, value in expected_keys_values.items():
                assert field in output.keys(), field + " can't be found int the output"
                assert value == output[field], "The value of {} is not {}".format(field, value)
