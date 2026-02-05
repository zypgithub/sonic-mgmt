import allure
import subprocess
import logging
import shlex
import concurrent.futures
from ngts.constants.constants import InfraConst

logger = logging.getLogger()


def run_process_on_host(cmd, timeout=60, exec_path=None, validate=False):
    logger.info('Executing command on remote host: {}'.format(cmd))
    p = subprocess.Popen(shlex.split(cmd), cwd=exec_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        std_out, std_err = p.communicate(timeout=timeout)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        logger.debug('Process is not responding. Sending SIGKILL.')
        p.kill()
        std_out, std_err = p.communicate()
        rc = p.returncode
        std_out = str(std_out.decode('utf-8') or '')
        std_err = str(std_err.decode('utf-8') or '')
    logger.debug('process:%s\n'
                 'rc:%s,\n'
                 'std_out:%s\n'
                 'std_err:%s', p.args, rc, std_out, std_err)

    logger.info('Command: {} finished execution'.format(cmd))

    if validate and rc != InfraConst.RC_SUCCESS:
        logger.error('process:%s\n'
                     'rc:%s,\n'
                     'std_out:%s\n'
                     'std_err:%s', p.args, rc, std_out, std_err)
        raise Exception('Command: {} execution failed'.format(p.args))

    return std_out, std_err, rc


def run_background_process_on_host(processes_dict, process_name, cmd, deploy_sequential=False, **kwargs):
    """
    Start process(run cmd) in background
    :param processes_dict: dict which contains threads names and objects
    :param process_name: name of process(will be displayed in Allure report)
    :param cmd: cmd which should be executed
    :param deploy_sequential: if True, run synchronously without a thread pool
    :param kwargs: kwargs
    :return: process obj
    """
    with allure.step(f'Starting background process: "{process_name}"'):
        if deploy_sequential:
            process_obj = concurrent.futures.Future()
            processes_dict[process_name] = process_obj
            try:
                result = run_process_on_host(cmd, **kwargs)
                process_obj.set_result(result)
            except Exception as e:
                process_obj.set_exception(e)
        else:
            process_executor = concurrent.futures.ThreadPoolExecutor()
            process_obj = process_executor.submit(run_process_on_host, cmd, **kwargs)
            # Release executor resources once the submitted task completes.
            # The future remains valid and the caller awaits it via wait_until_background_procs_done.
            process_executor.shutdown(wait=False)
            processes_dict[process_name] = process_obj

    return process_obj


def wait_until_background_procs_done(processes_dict):
    """
    Wait until background threads will finish and attach their output into Allure report
    :param processes_dict: list which contains threads objects
    """
    for proc_name, proc in processes_dict.items():
        with allure.step(f'Checking background process: "{proc_name}" results'):
            logger.info(f'Checking background process: "{proc_name}" results')
            std_out, std_err, rc = proc.result()

            result = ''
            if isinstance(std_out, str):
                result += f'STDOUT:\n {std_out} \n\n'
            else:
                try:
                    result += 'STDOUT:\n' + std_out.decode('utf-8') + '\n\n'
                except Exception as err:
                    result += 'STDOUT: failed to get process STDOUT, got error: {}\n'.format(err)

            if isinstance(std_err, str):
                result += f'STDERR:\n {std_err}'
            else:
                try:
                    result += 'STDERR:\n' + std_err.decode('utf-8')
                except Exception as err:
                    result += 'STDERR: failed to get process STDERR, got error: {}\n'.format(err)

            allure.attach(result, proc_name, allure.attachment_type.TEXT)
            if rc:
                raise AssertionError(f'Background thread process failed. '
                                     f'Check Allure report attached file: "{proc_name}" in step: "{proc_name}"')
