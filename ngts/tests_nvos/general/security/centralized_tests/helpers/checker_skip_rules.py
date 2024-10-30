import logging
from abc import ABC, abstractmethod
from typing import List, Dict


class CheckerSkipRule(ABC):
    @abstractmethod
    def should_skip_checker(self, dut_setup_name: str) -> bool:
        raise Exception(f"Not implemented for this class {self.__class__.__name__}")


class SkipCheckerBySetup(CheckerSkipRule):
    def __init__(self, setup_names: List[str], exclude: bool = True):
        self.setup_names: List[str] = setup_names
        self.exclude: bool = exclude

    def should_skip_checker(self, dut_setup_name: str) -> bool:
        is_dut_setup_name_in_rule_setups_list = any(name in dut_setup_name for name in self.setup_names)
        return is_dut_setup_name_in_rule_setups_list == self.exclude


class SkipCheckerByCond(CheckerSkipRule):
    def __init__(self, cond: bool):
        self.cond: bool = cond

    def should_skip_checker(self, dut_setup_name: str) -> bool:
        return self.cond


def should_skip_checker(skip_rules: Dict[str, CheckerSkipRule], checker_name: str, dut_setup_name: str) -> bool:
    if checker_name not in skip_rules:
        logging.info(f'there is no rule for checker "{checker_name}" - Not Skipping')
        return False
    res = skip_rules[checker_name].should_skip_checker(dut_setup_name)
    logging.info(f'checker "{checker_name}" - {"" if res else "Not "}Skipping')
    return res
