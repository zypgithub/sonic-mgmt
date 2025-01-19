import logging

from ngts.nvos_tools.infra.BaseComponent import BaseComponent


class Asic(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path="/asic")
        self.error_injection = ErrorInjection(self)


class ErrorInjection(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path="/error-injection")
