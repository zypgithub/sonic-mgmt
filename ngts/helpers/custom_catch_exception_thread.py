import threading
import logging
from infra.tools.exceptions.test_issue import TestIssue
from ngts.helpers.performance.Performance_log_print import print_players_logs

logger = logging.getLogger()


class CatchExceptionThread(threading.Thread):

    def __init__(self, target=None, name=None,
                 args=(), kwargs=None):
        super().__init__(target=target, name=name, args=args, kwargs=kwargs)

    def run(self):
        self.exc = None
        try:
            if self._target:
                self._target(*self._args, **self._kwargs)
        except Exception as e:
            self.exc = e
        finally:
            del self._target, self._args, self._kwargs

    def join(self, timeout=600):
        threading.Thread.join(self, timeout=timeout)
        if self.exc:
            raise self.exc


def parse_threads_exceptions_at_join(threads_list, players_info, step):
    exceptions = []
    players = []
    for th in threads_list:
        try:
            th.join()
        except Exception as e:
            logging.error(f"{th.name} - failed with Exception: {e}")
            players.append(th.name)
            player_hostname = players_info[th.name]['cli'].chassis.get_hostname()
            exceptions.append(f"{th.name} - {player_hostname} failed with Exception,please check thread logs\n")
            print_players_logs(players_list=players, players_info=players_info, print_to_stdout=True)
            raise TestIssue(f"Caught failure in {step}\n" + "\n".join(exceptions))
