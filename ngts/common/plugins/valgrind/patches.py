from typing import Callable
import functools
import inspect
import logging

logger = logging.getLogger(__name__)

# original attributes
_VG_BASE_DEVICE_ORIG_INIT_DUR_ATTR = "_vg_valgrind_orig_init_expected_op_durations"
_VG_DEPLOY_MEMVERIF_ORIG_WAIT_ATTR = "_vg_valgrind_deploy_memverif_orig_wait_until"
_VG_SSH_ORIG_READ_UNTIL_PATTERN_ATTR = "_vg_valgrind_orig_read_until_pattern"
_VG_SSH_ORIG_CONNECT_HANDLER_ATTR = "_vg_valgrind_orig_connect_handler"
_VG_SSH_ORIG_RUN_GET_ENGINE_ATTR = "_vg_valgrind_orig_run_get_engine"
_VG_SSH_ORIG_SEND_COMMAND_ATTR = "_vg_valgrind_orig_send_command"
_VG_SSH_ORIG_RUN_CMD_SET_ATTR = "_vg_valgrind_orig_run_cmd_set"
_VG_SSH_ORIG_FIND_PROMPT_ATTR = "_vg_valgrind_orig_find_prompt"

# applied attributes
_VG_DEPLOY_MEMVERIF_PATCH_APPLIED_ATTR = "_vg_valgrind_deploy_memverif_timeout_patch_applied"
_VG_PROXY_SSH_ENGINE_PATCH_APPLIED_ATTR = "_vg_valgrind_proxy_ssh_engine_patch_applied"
_VG_BASE_CONNECTION_PATCH_APPLIED_ATTR = "_vg_valgrind_base_connection_patch_applied"
_VG_BASE_DEVICE_PATCH_APPLIED_ATTR = "_vg_valgrind_base_device_patch_applied"
_VG_OP_DURATION_MULTIPLIER_ATTR = "_vg_valgrind_op_duration_multiplier"
_VG_SSH_MULTIPLIER_ATTR = "_vg_valgrind_ssh_timeout_multiplier"


def _valgrind_multiplier_decorator_factory(obj: object, attr: str, sig: inspect.Signature, key: str, arg_index: int) -> Callable:
    '''
    Decorator factory for patching functions with a multiplier.

    :param obj: The object to get the multiplier from.
    :param attr: The attribute for the multiplier that is patched to the object.
    :param sig: The signature of the function to patch.
    :param key: The key to patch in the kwargs or args.
    :param arg_index: The index of the argument to patch in the args.
    :return: A decorator that patches the function with a multiplier.
    '''
    def valgrind_multiplier_decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def valgrind_multiplier_wrapper(*args, **kwargs):
            multiplier = float(getattr(obj, attr, 1.0))
            logger.debug(f"[==PATCH==] Patching {func.__name__} {multiplier=} {args=} | {kwargs=}")

            # the argument name `key` is part of the kwargs
            if key in kwargs:
                kwargs[key] = kwargs[key] * multiplier

            # the argument name `key` is NOT part of the kwargs, but it is part of the args
            elif len(args) > arg_index:
                args = list(args)
                args[arg_index] = args[arg_index] * multiplier

            # the argument name `key` is NOT part of the kwargs, and it is NOT part of the args
            # so we need to override the default value
            else:
                kwargs[key] = sig.parameters[key].default * multiplier
            return func(*args, **kwargs)
        return valgrind_multiplier_wrapper
    return valgrind_multiplier_decorator


def _patch_wait_until_health_status_change_to(timeout_multiplier: float):
    '''
    Patch the System.wait_until_health_status_change_to function to increase the timeout.

    :param timeout_multiplier: The multiplier for the timeout.
    :return: None
    '''
    from ngts.nvos_tools.system.System import System
    from retry import retry

    wrapped = System.wait_until_health_status_change_to

    # outer wrapper is from `decorator` package
    outer = inspect.getclosurevars(wrapped).nonlocals
    caller = outer["caller"]  # <- this is retry.api.retry_decorator

    # inner closure has the real retry config
    inner = inspect.getclosurevars(caller).nonlocals
    tries = inner["tries"]
    delay = inner["delay"]
    exceptions = inner.get("exceptions", Exception)

    new_tries = int(tries * (max(1, timeout_multiplier * .5)))
    new_delay = delay * timeout_multiplier * 2

    base = wrapped.__wrapped__  # original undecorated wait_until_health_status_change_to

    System.wait_until_health_status_change_to = retry(exceptions, tries=new_tries, delay=new_delay)(base)


def _proxy_ssh_engine_patches(timeout_multiplier: float):
    '''
    Patch the proxy SSH engine to increase the timeouts.

    :param timeout_multiplier: The multiplier for the timeout.
    :return: None
    '''
    from infra.tools.connection_tools import proxy_ssh_engine

    setattr(proxy_ssh_engine, _VG_SSH_MULTIPLIER_ATTR, timeout_multiplier)

    # Make the patch idempotent across the entire pytest session (and safe under repeated calls).
    if getattr(proxy_ssh_engine, _VG_PROXY_SSH_ENGINE_PATCH_APPLIED_ATTR, False):
        old = getattr(proxy_ssh_engine, _VG_SSH_MULTIPLIER_ATTR, None)
        logger.debug("Valgrind SSH patch already applied; updated multiplier: %s -> %s", old, timeout_multiplier)
        return

    def _patched_connect_handler():
        from datetime import datetime, timezone
        setattr(proxy_ssh_engine, _VG_SSH_ORIG_CONNECT_HANDLER_ATTR, proxy_ssh_engine.ConnectHandler)

        def patched_connect_handler(*args, **kwargs):
            m = float(getattr(proxy_ssh_engine, _VG_SSH_MULTIPLIER_ATTR, 1.0))
            logger.debug(f"\033[93;1mPatching connect_handler\033[0m {m=} {args=} | {kwargs=}")
            kwargs['timeout'] = kwargs.get('timeout', 400) * m
            kwargs['session_timeout'] = kwargs.get('session_timeout', 400) * m
            kwargs['blocking_timeout'] = kwargs.get('blocking_timeout', 400) * m
            ts = datetime.now(timezone.utc)
            kwargs['session_log'] = f'/tmp/netmiko-{ts:%Y%m%d_%H%M%S}Z.log'
            kwargs['session_log_file_mode'] = 'append'
            kwargs['session_log_record_writes'] = True
            original: Callable = getattr(proxy_ssh_engine, _VG_SSH_ORIG_CONNECT_HANDLER_ATTR)
            return original(*args, **kwargs)

        proxy_ssh_engine.ConnectHandler = patched_connect_handler

    def _patched_get_engine():
        setattr(proxy_ssh_engine, _VG_SSH_ORIG_RUN_GET_ENGINE_ATTR, proxy_ssh_engine.ProxySshEngine.get_engine)

        def patched_get_engine(self: proxy_ssh_engine.ProxySshEngine):
            return self.get_engine_with_retry()

        proxy_ssh_engine.ProxySshEngine.get_engine = patched_get_engine

    def _patched_run_cmd_set():
        setattr(proxy_ssh_engine, _VG_SSH_ORIG_RUN_CMD_SET_ATTR, proxy_ssh_engine.ProxySshEngine.run_cmd_set)

        key = "tries_after_run_cmd"
        sig = inspect.signature(proxy_ssh_engine.ProxySshEngine.run_cmd_set)
        params = list(sig.parameters.values())
        index = [p.name for p in params].index(key)

        @_valgrind_multiplier_decorator_factory(proxy_ssh_engine, _VG_SSH_MULTIPLIER_ATTR, sig, key, index)
        def patched_run_cmd_set(self, *args, **kwargs):
            if key in kwargs:
                kwargs[key] = max(1, int(kwargs[key]))
            else:  # the `tries_after_run_cmd` is in the args
                args = list(args)
                # we have `self` in the patch func signature, the index is shifted by -1
                args[index - 1] = max(1, int(args[index - 1]))

            original: Callable = getattr(proxy_ssh_engine, _VG_SSH_ORIG_RUN_CMD_SET_ATTR)
            return original(self, *args, **kwargs)

        proxy_ssh_engine.ProxySshEngine.run_cmd_set = patched_run_cmd_set

    _patched_get_engine()
    _patched_run_cmd_set()
    _patched_connect_handler()

    setattr(proxy_ssh_engine, _VG_PROXY_SSH_ENGINE_PATCH_APPLIED_ATTR, True)


def _base_connection_patches(timeout_multiplier: float):
    '''
    Patch the BaseConnection to increase the timeouts.

    :param timeout_multiplier: The multiplier for the timeout.
    :return: None
    '''
    from netmiko import BaseConnection

    setattr(BaseConnection, _VG_SSH_MULTIPLIER_ATTR, timeout_multiplier)

    # Make the patch idempotent across the entire pytest session (and safe under repeated calls).
    if getattr(BaseConnection, _VG_BASE_CONNECTION_PATCH_APPLIED_ATTR, False):
        old = getattr(BaseConnection, _VG_SSH_MULTIPLIER_ATTR, None)
        logger.debug("Valgrind SSH patch already applied; updated multiplier: %s -> %s", old, timeout_multiplier)
        return

    def _patched_find_prompt():
        setattr(BaseConnection, _VG_SSH_ORIG_FIND_PROMPT_ATTR, BaseConnection.find_prompt)

        key = 'delay_factor'
        sig = inspect.signature(BaseConnection.find_prompt)
        params = list(sig.parameters.values())
        index = [p.name for p in params].index(key)

        @_valgrind_multiplier_decorator_factory(BaseConnection, _VG_SSH_MULTIPLIER_ATTR, sig, key, index)
        def patched_find_prompt(self, *args, **kwargs):
            original: Callable = getattr(BaseConnection, _VG_SSH_ORIG_FIND_PROMPT_ATTR)
            return original(self, *args, **kwargs)

        BaseConnection.find_prompt = patched_find_prompt

    def _patched_send_command():
        setattr(BaseConnection, _VG_SSH_ORIG_SEND_COMMAND_ATTR, BaseConnection.send_command)

        key = 'read_timeout'
        sig = inspect.signature(BaseConnection.send_command)
        params = list(sig.parameters.values())
        index = [p.name for p in params].index(key)

        @_valgrind_multiplier_decorator_factory(BaseConnection, _VG_SSH_MULTIPLIER_ATTR, sig, key, index)
        def patched_send_command(self, *args, **kwargs):
            original: Callable = getattr(BaseConnection, _VG_SSH_ORIG_SEND_COMMAND_ATTR)
            return original(self, *args, **kwargs)

        BaseConnection.send_command = patched_send_command

    def _patched_read_until_pattern():
        setattr(BaseConnection, _VG_SSH_ORIG_READ_UNTIL_PATTERN_ATTR, BaseConnection.read_until_pattern)

        key = 'read_timeout'
        sig = inspect.signature(BaseConnection.read_until_pattern)
        params = list(sig.parameters.values())
        index = [p.name for p in params].index(key)

        @_valgrind_multiplier_decorator_factory(BaseConnection, _VG_SSH_MULTIPLIER_ATTR, sig, key, index)
        def patched_read_until_pattern(self, *args, **kwargs):
            original: Callable = getattr(BaseConnection, _VG_SSH_ORIG_READ_UNTIL_PATTERN_ATTR)
            return original(self, *args, **kwargs)

        BaseConnection.read_until_pattern = patched_read_until_pattern

    _patched_find_prompt()
    _patched_send_command()
    _patched_read_until_pattern()

    setattr(BaseConnection, _VG_BASE_CONNECTION_PATCH_APPLIED_ATTR, True)


def _patch_expected_operation_durations(timeout_multiplier: float):
    '''
    Patch the BaseSwitch to increase the expected operation durations.

    :param timeout_multiplier: The multiplier for the timeout.
    :return: None
    '''
    from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch

    setattr(BaseSwitch, _VG_OP_DURATION_MULTIPLIER_ATTR, timeout_multiplier)

    # Make the patch idempotent across the entire pytest session (and safe under repeated calls).
    if getattr(BaseSwitch, _VG_BASE_DEVICE_PATCH_APPLIED_ATTR, False):
        old = getattr(BaseSwitch, _VG_OP_DURATION_MULTIPLIER_ATTR, None)
        logger.debug("Valgrind duration patch already applied; updated multiplier: %s -> %s", old, timeout_multiplier)
        return

    original = BaseSwitch._init_expected_operation_durations

    def patched_init_expected_operation_durations(self: BaseSwitch) -> None:
        original(self)

        m = max(1, float(getattr(BaseSwitch, _VG_OP_DURATION_MULTIPLIER_ATTR, 1.0)))

        key = "set hostname"
        if key not in self.expected_operation_durations:
            return

        base = self.expected_operation_durations[key]
        self.expected_operation_durations[key] *= (m * 5)
        logger.debug("Valgrind duration patch: %s %s -> %s (m=%s)", key, base, self.expected_operation_durations[key], m)

    setattr(BaseSwitch, _VG_BASE_DEVICE_ORIG_INIT_DUR_ATTR, original)
    BaseSwitch._init_expected_operation_durations = patched_init_expected_operation_durations
    setattr(BaseSwitch, _VG_BASE_DEVICE_PATCH_APPLIED_ATTR, True)


def maybe_patch_deploy_memverif_install_wait_timeout(pytest_timeout: int) -> None:
    """
    Workaround for NVOS `memverif` images that can take longer than the hardcoded deploy wait.

    Context:
      - `ngts/scripts/sonic_deploy/deploy_helper_methods.py` waits for the install background future with a fixed 1500s timeout.
      - For `memverif` images, the install can exceed that window.

    Policy:
      - Only apply when the Valgrind plugin is active AND the CLI option `--target-version` contains 'memverif'.
      - Use pytest's `--timeout` (pytest-timeout) as the upper bound for the install wait.
      - Keep behavior unchanged when `--timeout` isn't available or isn't a positive int.
    """
    # If pytest-timeout is set smaller than the deploy default, don't reduce behavior.
    try:
        from ngts.scripts.sonic_deploy.deploy_helper_methods import DeployOrchestrator
        if getattr(DeployOrchestrator, _VG_DEPLOY_MEMVERIF_PATCH_APPLIED_ATTR, False):
            return  # already patched

        original = DeployOrchestrator.wait_until_deploy_background_process
    except Exception as e:
        logger.error("Failed to patch DeployOrchestrator.wait_until_deploy_background_process: %s", e)
        logger.exception(e)
        return

    sig = inspect.signature(original)
    default_origin_timeout = sig.parameters['timeout'].default

    if pytest_timeout <= default_origin_timeout:
        logger.warning(f"pytest timeout is smaller than the default deploy wait timeout: {pytest_timeout=} <= {default_origin_timeout=}")
        return

    @staticmethod
    def wrapped_wait_until_deploy_background_process(install_threads, timeout=default_origin_timeout):
        return original(install_threads, timeout=max(timeout, pytest_timeout))

    setattr(DeployOrchestrator, _VG_DEPLOY_MEMVERIF_ORIG_WAIT_ATTR, original)
    DeployOrchestrator.wait_until_deploy_background_process = wrapped_wait_until_deploy_background_process
    setattr(DeployOrchestrator, _VG_DEPLOY_MEMVERIF_PATCH_APPLIED_ATTR, True)

    logger.info(
        "Valgrind plugin: patched DeployOrchestrator.wait_until_deploy_background_process for memverif deploy "
        "(max(timeout, pytest --timeout=%s [sec]))",
        pytest_timeout,
    )


def patch_ssh_engine(timeout_multiplier: float) -> None:
    """
    Patch the infra SSH engine to increase timeouts.

    :param timeout_multiplier: Multiplier for SSH timeouts (connect/session/blocking).
    """

    if timeout_multiplier <= 0:
        raise ValueError(f"--valgrind-multiplier must be > 0 (got {timeout_multiplier!r})")
    if timeout_multiplier < 1:
        logger.warning("Valgrind multiplier < 1 will reduce timeouts: %s", timeout_multiplier)

    with open('/tmp/valgrind.log', 'a') as f:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        f.write(f'{now:%Y-%m-%d %H:%M:%S}Z Valgrind mode enabled: timeout_multiplier={timeout_multiplier=:.2f}"\n')

    _patch_wait_until_health_status_change_to(timeout_multiplier)
    _patch_expected_operation_durations(timeout_multiplier)
    _proxy_ssh_engine_patches(timeout_multiplier)
    _base_connection_patches(timeout_multiplier)
