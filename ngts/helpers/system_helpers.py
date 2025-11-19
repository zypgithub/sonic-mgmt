import logging
import os
from retry.api import retry_call

logger = logging.getLogger()

JOBS_MAX_ATTEMPTS = 30
JOBS_POLLING_INTERVAL_SEC = 10


class PrefixEngine():

    def __init__(self, engine, prefix):
        self.engine = engine
        self.prefix = prefix

    def run_cmd(self, cmd, validate=False):
        return self.engine.run_cmd(f'{self.prefix} {cmd}', validate=validate)


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
