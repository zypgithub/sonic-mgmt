from typing import Dict
import allure
import logging

from ngts.nvos_constants.constants_nvos import RbacConsts
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict

logger = logging.getLogger()


class RbacClass(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/class')
        self.class_id: Dict[str, ClassId] = DefaultDict(
            lambda class_id: ClassId(parent=self, class_id=class_id))

    def set_new_class(self, classname=None, action=None, command_path=None, permission=None, engine=None, apply=False):
        with allure.step(f"setting up new class {classname} with {command_path}"):
            self.class_id[classname].set(op_param_name='action', op_param_value=action, dut_engine=engine).verify_result()

            if permission:
                self.class_id[classname].command_path.command_path_id[command_path].set(op_param_name=RbacConsts.PERMISSION, op_param_value=permission, dut_engine=engine, apply=apply).verify_result()
            else:
                self.class_id[classname].command_path.command_path_id[command_path].set(dut_engine=engine, apply=apply).verify_result()


class ClassId(BaseComponent):
    def __init__(self, parent, class_id):
        super().__init__(parent=parent, path=f'/{class_id}')
        self.classname = class_id
        self.action = BaseComponent(self, path='/action')
        self.command_path = CommandPath(self)

    def change_action(self, action, engine=None, apply=False):
        self.action.set(action, dut_engine=engine, apply=apply, ask_for_confirmation=True)

    def change_permission(self, command_path, permission, engine=None, apply=False):
        self.command_path.command_path_id[command_path].set(op_param_name=RbacConsts.PERMISSION, op_param_value=permission, dut_engine=engine, apply=apply, ask_for_confirmation=True)

    def show_command_path(self, command_path):
        return self.command_path.command_path_id[command_path].show(output_format=None)


class CommandPath(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/command-path')
        self.command_path_id: Dict[str, CommandPathId] = DefaultDict(
            lambda command_path_id: CommandPathId(parent=self, command_path_id=command_path_id))


class CommandPathId(BaseComponent):
    def __init__(self, parent, command_path_id):
        super().__init__(parent=parent, path='/' + command_path_id.replace('/', '%2F'))
        self.permission = BaseComponent(self, path='/permission')
