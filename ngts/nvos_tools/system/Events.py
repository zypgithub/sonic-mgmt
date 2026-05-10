import logging
from typing import Callable, Dict, List, Tuple

from ngts.nvos_constants.constants_nvos import ActionConsts, ApiType, SystemConsts
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tools.test_utils import allure_utils as allure


class Events(BaseComponent):
    """Wrapper for the `/system/events` resource.

    Exposes the events table via `show()` plus convenience helpers for getting the
    most-recent event, snapshotting a baseline event id, and filtering events by predicate.
    """

    def __init__(self, parent_obj: BaseComponent | None = None) -> None:
        BaseComponent.__init__(self, parent=parent_obj, path='/events')

    def show_events_last_recent_entries(self, query_param: str, events_count: str = '1') -> str:
        """Run `nv show system events --last|--recent <N>` (or its OpenAPI equivalent).

        `query_param` is one of SystemConsts.SYSTEM_LAST_EVENT / SYSTEM_RECENT_EVENT.
        `events_count` is the number of entries to return; an empty string falls back to 20
        for OpenAPI because `--last` is not supported there (RM-4396664).
        """
        query_param_api = f'?{query_param}'
        query_param_nvue = f'--{query_param}'
        events_count_api = f'={events_count}' if events_count else '=20'
        events_count_nvue = f' {events_count}'
        with allure.step("Show system event --last/--recent"):
            logging.info("Show system event --last/--recent")
            if TestToolkit.tested_api == ApiType.OPENAPI:
                return SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].show,
                                                       TestToolkit.get_engine(), self.get_resource_path(),
                                                       query_param_api + events_count_api).get_returned_value()
            else:
                return self.show(query_param_nvue + events_count_nvue)

    def action_clear(self) -> ResultObj:
        """Run `nv action clear system events` to wipe the events table."""
        return self.action(ActionConsts.CLEAR)

    def get_last(self) -> Dict[str, str]:
        """Return the most recently recorded event as a dict, or an empty dict if none."""
        events = OutputParsingTool.parse_json_str_to_dictionary(
            self.show_events_last_recent_entries(SystemConsts.SYSTEM_LAST_EVENT, '1')
        ).get_returned_value()
        return next(iter(events.values()), {})

    def get_max_event_id(self) -> int:
        """Return the highest numeric event id currently in the events table, or 0 if empty.

        Useful for snapshotting a baseline before an action so a follow-up assertion
        can ignore pre-existing events.
        """
        events = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
        return max((int(k) for k in events.keys() if str(k).isdigit()), default=0)

    def find_events(self, predicate: Callable[[Dict[str, str]], bool],
                    since_event_id: int = 0) -> List[Tuple[int, Dict[str, str]]]:
        """Return [(id, event_body), ...] for events with id > since_event_id where predicate(event_body) is True.

        Non-numeric keys (e.g. 'table-size', 'table-occupancy') and non-dict values are skipped.
        """
        events = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
        matches: List[Tuple[int, Dict[str, str]]] = []
        for eid, ev in events.items():
            if not str(eid).isdigit() or int(eid) <= since_event_id:
                continue
            if not isinstance(ev, dict):
                continue
            if predicate(ev):
                matches.append((int(eid), ev))
        return matches
