from typing import Dict

import logging
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict


logger = logging.getLogger()


class Role(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/role')
        self.role_id: Dict[str, RoleId] = DefaultDict(
            lambda role_id: RoleId(parent=self, role_id=role_id))

    def set_new_role(self, rolename, rbac_class, engine=None, apply=False):
        with allure.step(f"setting up new role {rolename} with class {rbac_class}"):
            self.role_id[rolename].class_rbac.class_rbac_id[rbac_class].set(dut_engine=engine, apply=apply, ask_for_confirmation=True).verify_result()


class RoleId(BaseComponent):
    def __init__(self, parent, role_id):
        super().__init__(parent=parent, path=f'/{role_id}')
        self.rolename = role_id
        self.class_rbac = ClassRbac(self)


class ClassRbac(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/class')
        self.class_rbac_id: Dict[str, ClassRbacId] = DefaultDict(
            lambda class_rbac_id: ClassRbacId(parent=self, class_rbac_id=class_rbac_id))


class ClassRbacId(BaseComponent):
    def __init__(self, parent, class_rbac_id):
        super().__init__(parent=parent, path=f'/{class_rbac_id}')
        self.classname = class_rbac_id
