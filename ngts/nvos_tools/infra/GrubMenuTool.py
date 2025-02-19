import logging
import time

import pexpect

from infra.tools.connection_tools.pexpect_serial_engine import PexpectSerialEngine
from ngts.tools.test_utils import allure_utils as allure


class GrubMenuTool:
    DIRECTION_UP = 'up'
    DIRECTION_DOWN = 'down'
    ARROW_UP_CHAR = "\x1b[A"
    ARROW_DOWN_CHAR = "\x1b[B"
    NUM_STEPS_TO_TOP = 6
    SELECTED_ITEM_PREFIX = '\\*'
    ESCAPE_CHAR = '\x1b'
    MAX_GRUB_ITEMS_LIMIT = 100
    GRUB_ESC_PATTERN = 'Press the ESC'
    NAVIGATION_FAILED = f'Grub menu navigation tool failed'

    @classmethod
    def _validate_direction_param(cls, direction: str):
        assert direction in [cls.DIRECTION_UP,
                             cls.DIRECTION_DOWN], f'{cls.NAVIGATION_FAILED}: wrong direction specified "{direction}"'

    @classmethod
    def _adjust_grub_menu_item_pattern(cls, item_pattern: str) -> str:
        if item_pattern.startswith(cls.SELECTED_ITEM_PREFIX):
            return item_pattern
        else:
            return cls.SELECTED_ITEM_PREFIX + item_pattern

    @classmethod
    def make_grub_menu_steps_in_one_direction(cls, serial_engine: PexpectSerialEngine, num_steps: int, direction: str,
                                              stop_cond: str = '', time_between_steps=0.1) -> bool:
        """
        make steps to given direction until condition is reached
        @param serial_engine:
        @param num_steps: number of steps to make (unless stop cond reached sooner)
        @param direction: direction of the navigation steps: up / down
        @param stop_cond: pattern to stop the steps if reached
        @param time_between_steps: delay between consecutive steps
        @return if stop cond is give, return whether stop cond reached. if not given, return True when done
        """
        cls._validate_direction_param(direction)

        arrow_char = cls.ARROW_UP_CHAR if direction == cls.DIRECTION_UP else cls.ARROW_DOWN_CHAR
        stop_cond = cls._adjust_grub_menu_item_pattern(stop_cond) if stop_cond else stop_cond

        with allure.step(
                f'go {direction} {num_steps} times' + (f', or till reaching "{stop_cond}"' if stop_cond else '')):
            for _ in range(num_steps):
                logging.info(f"Sending one arrow {direction}")
                if stop_cond:
                    try:
                        out, res_index = serial_engine.run_cmd(arrow_char, stop_cond, 0.2, True)
                        return True
                    except pexpect.exceptions.TIMEOUT:
                        pass
                else:
                    serial_engine.run_cmd(arrow_char, '.*', 1, True)
                    time.sleep(time_between_steps)

        return not stop_cond

    @classmethod
    def select_grub_menu_item(cls, serial_engine: PexpectSerialEngine, item_pattern, time_between_steps=0.1):
        """
        navigate in the current grub menu according to the specified num_steps_or_pattern
        @param serial_engine:
        @param item_pattern: pattern of grub menu item to be selected use as expect pattern to stop when reached
        @param time_between_steps:
        """
        item_reached = cls.make_grub_menu_steps_in_one_direction(serial_engine, cls.NUM_STEPS_TO_TOP, cls.DIRECTION_UP, item_pattern, time_between_steps)
        if not item_reached:
            item_reached = cls.make_grub_menu_steps_in_one_direction(serial_engine, cls.MAX_GRUB_ITEMS_LIMIT, cls.DIRECTION_DOWN, item_pattern, time_between_steps)
        assert item_reached, f'{cls.NAVIGATION_FAILED}: failed to navigate to item "{item_pattern}"'
