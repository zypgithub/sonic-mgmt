import logging
import os
from retry.api import retry_call
from typing import List, Any

logger = logging.getLogger()

JOBS_MAX_ATTEMPTS = 30
JOBS_POLLING_INTERVAL_SEC = 10


class PrefixEngine():

    def __init__(self, engine, prefix):
        self.engine = engine
        self.prefix = prefix

    def _prefixed(self, cmd: str) -> str:
        return f'{self.prefix} {cmd}' if self.prefix else cmd

    def run_cmd(self, cmd, validate=False, **kwargs):
        return self.engine.run_cmd(self._prefixed(cmd), validate=validate, **kwargs)

    def run_cmd_after_cmd(self, cmd_set: List[str], **kwargs) -> str:
        if not cmd_set:
            return self.engine.run_cmd_after_cmd(cmd_set, **kwargs)
        new_cmd_set = [self._prefixed(cmd_set[0])] + list(cmd_set[1:])
        return self.engine.run_cmd_after_cmd(new_cmd_set, **kwargs)

    def run_cmd_set(self, cmd_set: List[str], **kwargs) -> str:
        if not cmd_set:
            return self.engine.run_cmd_set(cmd_set, **kwargs)
        new_cmd_set = [self._prefixed(c) for c in cmd_set]
        return self.engine.run_cmd_set(new_cmd_set, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.engine, name)


def verify_empty_job_queue(engine):
    """
    Verifies that systemd job queue is empty.
    :param engine: the engine to use.
    :raise Exception: if the job queue is not empty.
    """
    if engine.run_cmd("sudo systemctl list-jobs | grep -v 'No jobs running.'"):
        raise Exception('Job queue is not empty')


def wait_for_all_jobs_done(engine, max_attempts=JOBS_MAX_ATTEMPTS, polling_interval_sec=JOBS_POLLING_INTERVAL_SEC):
    """
    Polls systemd job queue until it is empty.
    :param engine: the engine to use.
    :param max_attempts: the maximum number of attempts before failing with Exception
    :param polling_interval_sec: the polling interval in seconds
    :raise Exception: if the job queue was not empty after max_attempts have been made.
    """
    retry_call(verify_empty_job_queue,
               fargs=[engine],
               tries=max_attempts,
               delay=polling_interval_sec,
               logger=logger)


def copy_files_to_syncd(engine, files_list, directory, syncd_dir='/'):
    for file in files_list:
        logger.info(f'Copy {file} to syncd docker')
        dst = os.path.join('/tmp', file)
        engine.copy_file(source_file=os.path.join(directory, file),
                         dest_file=file,
                         file_system='/tmp',
                         direction='put'
                         )
        engine.run_cmd('docker cp {} {}'.format(dst, f'syncd:{syncd_dir}'))
        engine.run_cmd("sudo docker exec -i syncd bash -c 'chmod +x {}'".format(file))


def set_timezone(engine, timezone):
    if timezone == 'Israel':
        timezone = 'Asia/Jerusalem'
    engine.run_cmd(f'sudo timedatectl set-timezone {timezone}', validate=True)
