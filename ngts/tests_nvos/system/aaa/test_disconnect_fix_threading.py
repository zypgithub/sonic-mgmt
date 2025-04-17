import logging
import pytest
import time
from ngts.nvos_constants.constants_nvos import AclConsts
from ngts.nvos_constants.constants_nvos import ActionType, ApiType
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.SerialConsoleTool import SerialConsoleTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.cli_wrappers.nvue.nvue_system_clis import NvueSystemCli
from ngts.nvos_tools.system.Ssh import Ssh
from ngts.nvos_tools.acl.acl import Acl
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import CumulusConsts, RbacConsts
from netmiko.ssh_exception import NetmikoAuthenticationException
from infra.tools.exceptions.test_issue import TestIssue
import threading
from collections import defaultdict
import time
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.cli_wrappers.openapi.openapi_command_builder import OpenApiCommandHelper
from ngts.nvos_constants.constants_nvos import OpenApiReqType
from ngts.tests_nvos.general.security.radius.constants import RadiusPhysicalServer
from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts
from ngts.cli_wrappers.nvue.cumulus.cumulus_general_cli import CumulusGeneralCli

logger = logging.getLogger(__name__)

NOT_LOGGED_IN_ERROR_MSG = "User %s is not logged in"
NOT_EXIST_ERROR_MSG = "User %s is not Exists"
FORBIDDEN_MESSAGE = "Forbidden: You don't have the permission to access the requested resource."
INSUFFICIENT_PRIVILEGES_ERROR_MSG = "Error: No permission to execute this command"
ACTION_ERROR_MSG = "action_error: Only users with sudo class or system-admin classcan disconnect users."
SESSIONS_DELAY = 0.5
NEW_SSH_PORT1 = 40
NEW_SSH_PORT2 = 41
threads = []
sessions_dict = defaultdict(list)
sessions_dict_lock = threading.Lock()
cli_common = None


@pytest.fixture(scope='module', autouse=True)
def module_fixture(engines):
    """
    This fixture is used to create the engines object and the engines.dut connection password-free for sudo
    """
    global cli_common
    cli_common = CumulusGeneralCli(engines.dut, engines.dut)
    cli_common.modify_sudoers_for_cumulus()
    change_max_files(engines)
    increase_pty_limit(engines)

    yield


@pytest.fixture(scope='function', autouse=False)
def change_ssh():
    change_ssh_limits()
    yield


@pytest.fixture(scope='function', autouse=True)
def func_fixture(engines):

    yield

    ResultObj._pop_all_instances()
    threads.clear()
    sessions_dict.clear()


def rotate_logs(engines):
    """
    Reset the logs on the DUT.
    args:
        engines: The engines object
    """
    system = System(force_api=ApiType.NVUE)
    result = system.log.rotate_logs()
    return result


def resest_channels():
    """
    Reset the channels on the DUT.
    """
    all_sessions = []
    for sessions in sessions_dict.values():
        all_sessions.extend(sessions)
    for session in all_sessions:
        session.engine.read_channel()


def change_ssh_limits():
    """
    Change the SSH session limits in the sshd_config file.

    Args:
        number: The number to set for MaxSessions and calculate MaxStartups values
    """
    with allure.step('Modifying SSH session limits'):
        add_ssh_port(NEW_SSH_PORT1, '6')
        add_ssh_port(NEW_SSH_PORT2, '7')
        system = System(force_api=ApiType.NVUE)
        system.ssh_server.set("max-sessions-per-connection", 100)
        system.ssh_server.set("max-unauthenticated", f'"session-count" 500')
        system.ssh_server.set("max-unauthenticated", f'"throttle-percent" 30')
        system.ssh_server.set("max-unauthenticated", f'"throttle-start" 500')
        system.ssh_server.set("port", f"22,{NEW_SSH_PORT1},{NEW_SSH_PORT2}", apply=True, ask_for_confirmation='-y')


def add_ssh_port(port, rule_id):
    """
    Add a new SSH port to the sshd_config file.

    Args:
        engines: The test engines object containing the DUT connection
        port: The port to add to the sshd_config file
        rule_id: The rule ID to add to the sshd_config file
    """
    with allure.step('Add a new SSH port to the nv config'):
        acl = Acl()
        acl_rule = acl.acl_id["acl-default-whitelist"].rule.rule_id[rule_id]
        acl_rule.match.ip.set_protocol(AclConsts.TCP)
        acl_rule.match.ip.tcp.set("dest-port", port)
        acl_rule.match.ip.set("connection-state", "new")
        acl_rule.match.ip.set("connection-state", "established")
        acl_rule.action.set('permit', apply=True)


def check_error_message(response):
    """
    Check if the error message is in the response.
    Args:
        response: The response from the API
    """
    assert (ACTION_ERROR_MSG in response or FORBIDDEN_MESSAGE in response), f"Expected '{ACTION_ERROR_MSG}' or '{FORBIDDEN_MESSAGE}' error, got: {response}"


def change_max_files(engines, max_files=65535):
    """
    Edit /etc/security/limits.conf to set maximum file descriptor limits for all users.
    Also set the current session limits using ulimit.

    Args:
        max_files (int): Maximum number of file descriptors to set. Default is 65535.

    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        # Create backup of original file
        engines.dut.run_cmd("sudo cp /etc/security/limits.conf /etc/security/limits.conf.backup")

        # Add new limits for all users
        limits_entry = f"* soft nofile {max_files}\n* hard nofile {max_files}\n"

        if limits_entry not in cli_common.read_file('/etc/security/limits.conf', is_sudo=True):
            # Append the new limits to the file
            cmd = f'echo "{limits_entry}" | sudo tee -a /etc/security/limits.conf'
            engines.dut.run_cmd(cmd)
            logger.info(f"Limits entry added to /etc/security/limits.conf: {limits_entry}")

        # Set current session limits using ulimit
        engines.dut.run_cmd(f"ulimit -n {max_files}")  # Set soft limit
        engines.dut.run_cmd(f"ulimit -Hn {max_files}")  # Set hard limit

        # Verify the limits were set correctly
        soft_limit = engines.dut.run_cmd("ulimit -n").strip()
        hard_limit = engines.dut.run_cmd("ulimit -Hn").strip()
        logger.info(f"Current file descriptor limits - Soft: {soft_limit}, Hard: {hard_limit}")

        return True
    except Exception as e:
        logger.error(f"Error setting file descriptor limits: {str(e)}")
        # Restore backup if operation failed
        engines.dut.run_cmd("sudo cp /etc/security/limits.conf.backup /etc/security/limits.conf")
        return False


def increase_pty_limit(engines, max_ptys=65535):
    """
    Increase the number of PTY devices available on the system.

    Args:
        engines: The test engines object containing the DUT connection information
        max_ptys (int): Maximum number of PTY devices to set. Default is 65535.

    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        # Check current PTY limit
        current_limit = engines.dut.run_cmd("cat /proc/sys/kernel/pty/max").strip()
        logger.info(f"Current PTY limit: {current_limit}")

        # Increase the limit
        engines.dut.run_cmd(f"echo {max_ptys} | sudo tee /proc/sys/kernel/pty/max")

        # Verify the new limit
        new_limit = engines.dut.run_cmd("cat /proc/sys/kernel/pty/max").strip()
        logger.info(f"New PTY limit: {new_limit}")

        # Make the change permanent by adding to sysctl.conf
        sysctl_entry = f"kernel.pty.max = {max_ptys}"
        if sysctl_entry not in cli_common.read_file('/etc/sysctl.conf', is_sudo=True):
            engines.dut.run_cmd(f'echo "{sysctl_entry}" | sudo tee -a /etc/sysctl.conf')
            engines.dut.run_cmd("sudo sysctl -p")

        return True
    except Exception as e:
        logger.error(f"Error increasing PTY limit: {str(e)}")
        return False


def add_ssh_key_to_localhost(engines, username):
    """
    Generate an SSH key pair on the DUT and copy it to localhost for passwordless authentication.

    This function:
    1. Generates an SSH key pair on the DUT if it doesn't exist
    2. Copies the public key to localhost for the specified user
    3. Sets appropriate permissions on the SSH directory and files

    Args:
        engines: The test engines object containing the DUT connection information
        username (str): Username to add the SSH key for
        password (str, optional): Password for the user if needed for authentication

    Returns:
        bool: True if successful, False otherwise

    Example:
        >>> success = add_ssh_key_to_localhost(engines, "admin")
        >>> if success:
        >>>     print("SSH key added successfully")
    """
    with allure.step(f'Add SSH key for user "{username}" to localhost'):
        try:
            # Check if .ssh directory exists, create if not
            engines.dut.run_cmd(f'sudo mkdir -p /home/{username}/.ssh')
            engines.dut.run_cmd(f'sudo chown {username}:{username} /home/{username}/.ssh')
            engines.dut.run_cmd(f'sudo chmod 700 /home/{username}/.ssh')

            # Check if key already exists
            key_exists = engines.dut.run_cmd(f'test -f /home/{username}/.ssh/id_rsa && echo "exists" || echo "not exists"')

            if 'exists' not in key_exists:
                # Generate SSH key pair
                engines.dut.run_cmd(f'sudo -u {username} ssh-keygen -t rsa -b 2048 -f /home/{username}/.ssh/id_rsa -N ""')
                engines.dut.run_cmd(f'sudo chown {username}:{username} /home/{username}/.ssh/id_rsa*')
                engines.dut.run_cmd(f'sudo chmod 600 /home/{username}/.ssh/id_rsa')
                engines.dut.run_cmd(f'sudo chmod 644 /home/{username}/.ssh/id_rsa.pub')

            # Get the public key
            public_key = engines.dut.run_cmd(f'cat /home/{username}/.ssh/id_rsa.pub')

            # Add the key to localhost's authorized_keys
            engines.dut.run_cmd(f'sudo mkdir -p /root/.ssh')
            engines.dut.run_cmd(f'sudo touch /root/.ssh/authorized_keys')
            engines.dut.run_cmd(f'sudo chmod 700 /root/.ssh')
            engines.dut.run_cmd(f'sudo chmod 600 /root/.ssh/authorized_keys')

            # Check if key already in authorized_keys to avoid duplicates
            key_check = engines.dut.run_cmd(f'grep -F "{public_key.strip()}" /root/.ssh/authorized_keys || echo "not found"')

            if 'not found' in key_check:
                engines.dut.run_cmd(f'echo "{public_key}" | sudo tee -a /root/.ssh/authorized_keys')

            # Also add to the user's own authorized_keys for self-connection
            engines.dut.run_cmd(f'sudo touch /home/{username}/.ssh/authorized_keys')
            engines.dut.run_cmd(f'sudo chown {username}:{username} /home/{username}/.ssh/authorized_keys')
            engines.dut.run_cmd(f'sudo chmod 600 /home/{username}/.ssh/authorized_keys')

            key_check = engines.dut.run_cmd(f'grep -F "{public_key.strip()}" /home/{username}/.ssh/authorized_keys || echo "not found"')

            if 'not found' in key_check:
                engines.dut.run_cmd(f'echo "{public_key}" | sudo tee -a /home/{username}/.ssh/authorized_keys')

            logger.info(f"SSH key for user {username} successfully added to localhost")
            return True

        except Exception as e:
            logger.error(f"Failed to add SSH key for user {username}: {str(e)}")
            return False


def run_nginx(engines):
    """
    Run the nginx service on the DUT.
    """
    # Verify Nginx runs
    with allure.step('Verify Nginx runs before test'):
        nginx_status = engines.dut.run_cmd('systemctl status nginx')
        if not 'active (running)' in nginx_status:
            engines.dut.run_cmd('sudo systemctl start nginx')


def create_user(system, username, password=None, apply=False):
    """
    Create a new user in the system with specified or randomly generated credentials.

    This function creates a new user in the system using the AAA user management interface.
    If no password is provided, a random password will be generated. The function can either
    apply the changes immediately or defer the application based on the apply parameter.

    Args:
        system: System object that provides AAA user management functionality
        username (str): The username to create
        password (str, optional): Password for the user. If None, a random password will be generated
        apply (bool, optional): Whether to apply the changes immediately. Defaults to True

    Returns:
        tuple: A tuple containing (username, password) where:
            - username (str): The created username
            - password (str): The password for the user (either provided or generated)

    Example:
        >>> system = System()
        >>> username, password = create_user(system, "testuser")
        >>> print(f"Created user {username} with password {password}")
    """
    with allure.step(f'Create user "{username}"'):
        # Generate random password if not provided
        if password is None:
            username, password = system.aaa.user.set_new_user(username=username, apply=apply)
        else:
            username, _ = system.aaa.user.set_new_user(username=username, password=password, apply=apply)
        return username, password


def disconnect_user_open_api(engines, disconnect_user, disconnect_pass, user_to_disconnect=None):
    """
    Disconnect a user using the REST API.
    """
    params = {"state": "start"}
    path = f'/system/aaa/user/{user_to_disconnect}' if user_to_disconnect else '/system/aaa/user'
    response = OpenApiCommandHelper.execute_action(ActionType.DISCONNECT, disconnect_user, disconnect_pass, engines.dut.ip, path, params=params)
    return response


def create_session(engines, user, password, port=22):
    """
    Create a single SSH session for a user with retry mechanism.

    Args:
        engines: The test engines object containing the DUT connection information
        user (str): Username to create the session for
        password (str): Password for the user

    Returns:
        ConnectionTool: An SSH session object for the specified user
        port (int): Port to connect to
    Example:
        >>> session = create_session(engines, "admin", "password123")
        >>> session.run_cmd("show version")
    """
    with allure.step(f'Create session for user "{user}"'):
        max_retries = 5
        retry_count = 0

        while retry_count < max_retries:
            try:
                session_result = ConnectionTool.create_ssh_conn(engines.dut.ip, user, password, port, retry=False)
                if session_result.result:
                    session = session_result.get_returned_value()
                    with sessions_dict_lock:
                        sessions_dict[user].append(session)
                    return session
            except Exception as e:
                retry_count += 1
                if retry_count == max_retries:
                    raise  # Re-raise the last exception if we've exhausted all retries
                logger.warning(f"Authentication failed for user {user}, attempt {retry_count} of {max_retries} with error: {str(e)}")
            time.sleep(1)  # Add a small delay between retries


def create_session_thread(engines, user, password, port=22):
    thread = threading.Thread(target=create_session, args=(engines, user, password, port))
    threads.append(thread)
    thread.start()


def wait_for_sessions_threads():
    for thread in threads:
        thread.join()


def create_sessions(engines, user, password, count, port=22, sleep=0):
    """
    Create multiple sessions for a user by calling create_session count times.

    Args:
        engines: The test engines object containing the DUT connection information
        user (str): Username to create the sessions for
        password (str): Password for the user
        count (int): Number of sessions to create

    Returns:
        list: List of ConnectionTool objects representing the created SSH sessions

    Example:
        >>> sessions = create_sessions(engines, "admin", "password123", 3)
        >>> for session in sessions:
        ...     session.run_cmd("show version")
    """
    with allure.step(f'Create {count} sessions for user "{user}"'):
        # Create sessions with a delay between them to avoid overwhelming the system
        for i in range(count):
            create_session_thread(engines, user, password, port)
            time.sleep(sleep)


def disconnect_user(session, user=None, force_foreground=False, validate=True, serial_engine=False, retry_run=True):
    """
    Disconnect a user or all users from the system using the specified session.

    This function handles both foreground and background disconnection scenarios.
    For self-disconnection or disconnecting all users, it uses background execution
    to prevent the session from being terminated before the command completes.

    Args:
        session: The session object to execute the disconnect command from
        user (str, optional): Username to disconnect. If None, disconnects all users
        force_foreground (bool, optional): Force foreground execution even for self-disconnect.
            Defaults to False.

    Note:
        - For self-disconnection or disconnecting all users, the command runs in background
        - For disconnecting other users, the command runs in foreground
        - The function waits up to TIMEOUT seconds for the session to close
        - A warning is logged if the session doesn't close within the timeout period

    Example:
        >>> # Disconnect specific user
        >>> disconnect_user(session, "user1")
        >>> # Disconnect all users
        >>> disconnect_user(session)
        >>> # Force foreground execution
        >>> disconnect_user(session, "user1", force_foreground=True)
    """
    TIMEOUT = 20
    system = System(force_api=ApiType.NVUE)
    if user is None:
        # Disconnect all users
        try:
            result = system.aaa.user.action('disconnect', engine=session)
        except Exception as e:
            logger.warning(f"Disconnecting all users caused: {str(e)}")
            result = "Exception " + str(e)
            return result
    else:
        # Disconnect specific user
        try:
            result = system.aaa.user.user_id[user].action('disconnect', engine=session)
        except Exception as e:
            logger.warning(f"Exception while disconnecting user {user}: {str(e)}")
            result = "Exception " + str(e)
            return result
    if not result.result:
        result = "Failure " + result.info
    return result


def disconnect_user_serial_connection(session, user=None, force_foreground=False, validate=True, serial_engine=False, retry_run=True):
    """
    Disconnect a user or all users from the system using the specified session.
    """
    TIMEOUT = 20
    system = System(force_api=ApiType.NVUE)
    try:
        path = f"system aaa user {user}" if user else "system aaa user"
        result = NvueSystemCli.action_disconnect(engine=session, path=path)
    except Exception as e:
        logger.warning(f"Disconnecting user {user} caused: {str(e)}")
        result = str(e)
    return result


def verify_sessions_disconnected(engines, user):
    """
    Verify that a user has no active sessions on the system.

    This function checks the output of the 'who -u' command to ensure that
    the specified user has no active sessions. It raises an assertion error
    if the user is found to have any active sessions.

    Args:
        engines: The test engines object containing the DUT connection
        user (str): Username to check for active sessions

    Raises:
        AssertionError: If the user is found to have any active sessions

    Example:
        >>> # Verify user has no active sessions
        >>> verify_sessions_disconnected(engines, "user1")
        >>> # If user has active sessions, this will raise an AssertionError
        >>> verify_sessions_disconnected(engines, "user2")  # Raises: User user2 is still active
    """
    time.sleep(1)
    with allure.step(f'Verify sessions disconnected for user "{user}"'):
        current_sessions = cli_common.who('-u')
        assert user not in current_sessions, f"User {user} is still active"


def verify_sessions_active(engines, user, expected_num_sessions=1):
    """
    Verify that a user has active sessions on the system.

    This function checks the output of the 'who -u' command to ensure that
    the specified user has active sessions. It raises an assertion error
    if the user is found to not have any active sessions.

    Args:
        engines: The test engines object containing the DUT connection
        user (str): Username to check for active sessions
        expected_num_sessions (int): Expected number of active sessions
    Raises:
        AssertionError: If the user is found to not have any active sessions

    Example:
        >>> # Verify user has active sessions
        >>> verify_sessions_active(engines, "user1")
        >>> # If user has no active sessions, this will raise an AssertionError
        >>> verify_sessions_active(engines, "user2")  # Raises: User user2 is not active
    """
    with allure.step(f'Verify sessions active for user "{user}"'):
        current_sessions = cli_common.who('-u')
        if expected_num_sessions == 1:
            assert user in current_sessions, f"User {user} is not active"
        else:
            assert current_sessions.count(user) == expected_num_sessions, f"User {user} is missing sessions"


def verify_syslog_updated_successfully(engines, users, expected_msg_counts_for_users, action_disconnect_should_fail=False):
    """
    Verify that the syslog has been updated successfully for the given users.
    """
    # Verify syslog updates
    with allure.step('Verify syslog updates'):
        new_syslog_entries = cli_common.read_file('/var/log/syslog', is_sudo=True)
        # Verify disconnect commands are logged
        if not action_disconnect_should_fail:
            for user, count in zip(users, expected_msg_counts_for_users):
                # Each user session should have exactly one disconnect command logged
                assert new_syslog_entries.count(f"session closed for user {user}") == count, f"Syslog should contain exactly one disconnect command for session closed for user {user}"
        else:
            for user in users:
                assert f"session closed for user {user}" not in new_syslog_entries, f"Syslog should not contain session closed message for user {user}"


def verify_nvued_updated_successfully(engines, users, action_disconnect_should_fail=False, unprivileged_user=None):
    """
    Verify that the nvued has been updated successfully for the given users.
    """
    # Verify nvued log updates
    with allure.step('Verify nvued log updates'):
        new_nvued_entries = cli_common.read_file('/var/log/nvued.log', is_sudo=True)
        if not action_disconnect_should_fail:
            for user in users:
                assert f"running ActionKey('@disconnect', '/system/aaa/user/{{user-id}}', ('{user}'" in new_nvued_entries, f"nvued log should contain disconnect operation for user {user}"
        else:
            # Verify insufficient privileges messages for individual disconnects
            for user in users:
                assert f"Denying '{unprivileged_user}' from performing POST /nvue_v1/system/aaa/user/{user} because: insufficient privileges" in new_nvued_entries, f"nvued log should contain insufficient privileges message for user {unprivileged_user}"
            # Verify insufficient privileges message for disconnect all
            assert f"Denying '{unprivileged_user}' from performing POST /nvue_v1/system/aaa/user because: insufficient privileges" in new_nvued_entries, f"nvued log should contain insufficient privileges message for disconnect all for user {unprivileged_user}"


def verify_nvued_log_updated_successfully_disconnect_all(engines, users):
    """
    Verify that the nvued log has been updated successfully for the given users.
    """
    # Verify nvued log updates
    with allure.step('Verify nvued log updates'):
        new_nvued_entries = cli_common.read_file('/var/log/nvued.log', is_sudo=True)
        assert f"Ran Job running ActionKey('@disconnect', '/system/aaa/user'" in new_nvued_entries, f"nvued log should contain disconnect operation for all users"


def verify_logs_updated_successfully(engines, users, expected_msg_counts_for_users, negative=False, negative_user=None):
    """
    Verify that the logs have been updated successfully for the given user.

    Args:
        engines: The test engines object containing the DUT connection
        users: The list of users to verify the logs for

    Returns:
        bool: True if the logs have been updated successfully, False otherwise
    """
    verify_syslog_updated_successfully(engines, users, expected_msg_counts_for_users, negative)
    verify_nvued_updated_successfully(engines, users, negative, negative_user)
    return True


def verify_logs_updated_successfully_disconnect_all(engines, users, expected_msg_counts_for_users):
    """
    Verify that the logs have been updated successfully for the given users.

    Args:
        engines: The test engines object containing the DUT connection
        users: The list of users to verify the logs for
        counts: The list of counts to verify the logs for

    Returns:
        bool: True if the logs have been updated successfully, False otherwise
    """
    verify_syslog_updated_successfully(engines, users, expected_msg_counts_for_users)
    verify_nvued_log_updated_successfully_disconnect_all(engines, users)
    return True


def get_all_users(engines):
    """
    Get all users using the User API.

    Args:
        engines: The test engines object containing the DUT connection

    Returns:
        list: List of usernames configured in the system
    """
    system = System(force_api=ApiType.NVUE)
    users = list(system.aaa.user.parse_show(dut_engine=engines.dut).keys())
    return users


def get_user_role(engines, username: str):
    """
    Get the role of a specific user using the User API.

    Args:
        engines: The test engines object containing the DUT connection
        username: The username to get the role for

    Returns:
        str: The role of the user
    """
    system = System(force_api=ApiType.NVUE)
    user = system.aaa.user.user_id[username]
    user_info = user.parse_show(dut_engine=engines.dut)
    return user_info.get('role')


def add_user_with_sudo(engines, username, password=None):
    """
    Add a new user with sudo permissions.

    Args:
        engines: The test engines object containing the DUT connection
        username: The username to create
        password: Optional password for the user. If not provided, a random password will be generated

    Returns:
        tuple: (username, password) - The username and password of the created user
    """
    with allure.step(f'Add user "{username}" with sudo permissions'):
        system = System(force_api=ApiType.NVUE)

        # Generate random password if not provided
        if password is None:
            username, password = system.aaa.user.set_new_user(username=username, apply=True)
        else:
            username, _ = system.aaa.user.set_new_user(username=username, password=password, apply=True)

        # Add user to sudo group
        engines.dut.run_cmd(f'sudo usermod -aG sudo {username}')

        # Verify user was created and has sudo permissions
        users = get_all_users(engines)
        assert username in users, f"User {username} was not created"

        # Verify sudo group membership
        groups = engines.dut.run_cmd(f'groups {username}')
        assert 'sudo' in groups, f"User {username} was not added to sudo group"

        return username, password


def add_user_with_system_admin(engines, username, password=None, apply=False):
    """
    Add a new user with system-admin permissions.

    Args:
        engines: The test engines object containing the DUT connection
        username: The username to create
        password: Optional password for the user. If not provided, a random password will be generated

    Returns:
        tuple: (username, password) - The username and password of the created user
    """
    with allure.step(f'Add user "{username}" with system-admin permissions'):
        system = System(force_api=ApiType.NVUE)

        _user, _password = system.aaa.user.set_new_user(username=username,
                                                        password=password,
                                                        role=CumulusConsts.ROLE_SYSTEM_ADMIN,
                                                        apply=apply)

        if apply:
            # Verify user was created and has system-admin role
            users = get_all_users(engines)
            assert username in users, f"User {username} was not created"
            user_role = get_user_role(engines, username)
            assert user_role == CumulusConsts.ROLE_SYSTEM_ADMIN, f"User {username} was not assigned system-admin role"

        return _user, _password


def check_disconnection_messages(sessions):
    """
    Check if the sessions received the expected messages.
    """
    for session in sessions:
        if f"Session disconnected by NVUE as 'nv action disconnect system aaa user {session.username}' called" in session.engine.read_channel():
            return True
    logger.warning(f"User {session.username} should have received disconnect message")
    return False


def verify_sessions_state(engines, users_sessions_should_be_closed=[], users_sessions_should_be_active=[]):
    """
    Verify the state of multiple user sessions in the system.

    This function checks if specified sessions are either closed or active as expected.
    It performs two types of verification:
    1. For sessions that should be closed:
       - Verifies the session object's is_closed flag is True
       - Verifies the username is not present in the current active sessions
    2. For sessions that should be active:
       - Verifies the session object's is_closed flag is False
       - Verifies the username is present in the current active sessions

    Args:
        engines: The test engines object containing the DUT connection
        users_sessions_should_be_closed (list): List of session objects that should be closed
        users_sessions_should_be_active (list): List of session objects that should be active

    Raises:
        AssertionError: If any session's state does not match the expected state

    Example:
        >>> verify_sessions_state(engines,
        ...                      users_sessions_should_be_closed=[session1, session2],
        ...                      users_sessions_should_be_active=[session3])
    """
    time.sleep(5)
    current_sessions = cli_common.who('-u')
    for session in users_sessions_should_be_closed:
        assert session.username not in current_sessions, f"{session.username} session is still active"

    for session in users_sessions_should_be_active:
        assert session.username in current_sessions, f"{session.username} session is not active"


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test01_user_disconnect(engines):
    """
    Test that users with sudo permissions as well as system_admin can disconnect users,
    users with single session, as well as user with multiple sessions. Verify termination
    messages and syslog updates.

    Procedure:
    1. Create a super user with sudo permissions
    2. Create a system admin user
    3. Create 6 regular users (user1-user6), with sudo permissions for user3 and user6
    4. Create sessions:
       - Single session for user1, user4
       - Three sessions for user2, user5
       - Single session for user3, user6
    5. Create two sessions each for system_admin and super
    6. System admin disconnects user1, user2, user3 from first session
       - Verify only first system_admin session receives success messages
       - Verify second system_admin session remains active
    7. Super disconnects user4, user5, user6 from first session
       - Verify only first super session receives success messages
       - Verify second super session remains active
    8. Super disconnects system_admin
    9. Verify only super sessions remain active
    10. Verify syslog contains:
        - One "session closed" message per user's session
        - One "Successfully disconnected" message per user
    11. Verify nvued log contains:
        - One disconnect operation per user
        - One disconnect message per user
    """
    system = System(force_api=ApiType.NVUE)
    with allure.step('Create users for test'):
        # Create system admin user
        system_admin, system_admin_pass = add_user_with_system_admin(engines, 'system_admin')

        # Create super user with sudo permissions
        super_user, super_pass = add_user_with_sudo(engines, 'super')

        # Create regular users
        user1, pass1 = create_user(system, 'user1')
        user2, pass2 = create_user(system, 'user2')
        user3, pass3 = add_user_with_sudo(engines, 'user3')
        user4, pass4 = create_user(system, 'user4')
        user5, pass5 = create_user(system, 'user5')
        user6, pass6 = add_user_with_sudo(engines, 'user6')

    with allure.step('Create sessions for all users'):
        # Create sessions for all users
        create_session_thread(engines, user1, pass1)
        create_session_thread(engines, user4, pass4)

        create_sessions(engines, user2, pass2, 3)
        create_sessions(engines, user5, pass5, 3)

        create_session_thread(engines, user3, pass3)
        create_session_thread(engines, user6, pass6)

        # Create two sessions each for system_admin and super
        create_sessions(engines, system_admin, system_admin_pass, 2)
        create_sessions(engines, super_user, super_pass, 2)

        # Wait for all threads to complete and get the actual session objects
        wait_for_sessions_threads()
        resest_channels()

    rotate_logs(engines)

    # System admin disconnects user1, user2, user3 from first session
    with allure.step('System admin disconnects users and verify termination messages'):
        # Capture output from sessions
        for user in [user1, user2, user3]:
            disconnect_user(sessions_dict[system_admin][0], user)
            # assert "Action succeeded" in output, "First system_admin session should receive success message"
            check_disconnection_messages(sessions_dict[user])

        # Verify second session remains active and didn't receive messages
        assert not sessions_dict[system_admin][1].is_closed, "Second system_admin session should remain active"
        assert len(sessions_dict[system_admin][1].engine.read_channel()) == 0, "Second system_admin session should not receive disconnect messages"

    # Super disconnects user4, user5, user6 from first session
    with allure.step('Super disconnects users and verify termination messages'):
        for user in [user4, user5, user6]:
            disconnect_user(sessions_dict[super_user][0], user)
            # assert "Action succeeded" in output, "First super session should receive success message"
            check_disconnection_messages(sessions_dict[user])

        # Verify second session remains active and didn't receive messages
        assert not sessions_dict[super_user][1].is_closed, "Second super session should remain active"
        assert len(sessions_dict[super_user][1].engine.read_channel()) == 0, "Second super session should not receive disconnect messages"

    with allure.step('Super disconnects system_admin'):
        # Super disconnects system_admin
        disconnect_user(sessions_dict[super_user][0], system_admin)

    # Verify only super sessions are active
    verify_sessions_state(engines,
                          users_sessions_should_be_closed=sessions_dict[user1] + sessions_dict[user4] +
                          sessions_dict[user2] + sessions_dict[user5] +
                          sessions_dict[user3] + sessions_dict[user6] +
                          sessions_dict[system_admin],
                          users_sessions_should_be_active=sessions_dict[super_user])

    users = [user1, user2, user3, user4, user5, user6, system_admin]
    expected_msg_counts_for_users = [1, 3, 1, 1, 3, 1, 2]

    verify_logs_updated_successfully(engines, users, expected_msg_counts_for_users)

    # Clean up
    sessions_dict[super_user][0].disconnect()
    sessions_dict[super_user][1].disconnect()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test02_privileged_users_disconnect_thyself(engines):
    """
    Test that users with sudo permissions as well as system_admin can disconnect themselves.

    Procedure:
    1. Create a user with sudo permissions - super, and a user with base permissions
    2. Start a single session with system_admin, super, user
    3. Disconnect super from super
    4. Disconnect system_admin from system_admin
    5. Verify that only user has a session
    6. Verify syslog contains:
       - One "session closed" message per user's session
       - One "Successfully disconnected" message per user
    7. Verify nvued log contains:
       - One disconnect operation per user
       - One disconnect message per user
    """
    system = System(force_api=ApiType.NVUE)
    # Create users
    system_admin, system_admin_pass = add_user_with_system_admin(engines, 'system_admin')
    regular_user, regular_pass = create_user(system, 'regular_user')
    super_user, super_pass = add_user_with_sudo(engines, 'super')

    # Create sessions using threading
    create_session_thread(engines, super_user, super_pass)
    create_session_thread(engines, system_admin, system_admin_pass)
    create_session_thread(engines, regular_user, regular_pass)

    # Wait for all threads to complete and get the actual session objects
    wait_for_sessions_threads()
    resest_channels()

    rotate_logs(engines)

    # Disconnect super from itself
    disconnect_user(sessions_dict[super_user][0], super_user, retry_run=False)

    # Disconnect system_admin from itself
    disconnect_user(sessions_dict[system_admin][0], system_admin, retry_run=False)

    # Verify only regular user has an active session
    verify_sessions_state(engines,
                          users_sessions_should_be_closed=sessions_dict[super_user] + sessions_dict[system_admin],
                          users_sessions_should_be_active=sessions_dict[regular_user])

    verify_logs_updated_successfully(engines, [super_user, system_admin], [1, 1])

    # Clean up
    sessions_dict[regular_user][0].disconnect()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test03_system_admin_user_disconnect_all(engines):
    """
    Connect with system_admin user and disconnect all users.

    Procedure:
    1. Connect with system_admin user
    2. Create and connect with user1,..., user3, each with i sessions
    3. Disconnect all users
    4. Verify system_admin and other users are disconnected
    5. Verify syslog contains:
       - One "session closed" message per user's session
       - One "Successfully disconnected" message per user
    6. Verify nvued log contains:
       - One disconnect operation per user
       - One disconnect message per user
    """
    system = System(force_api=ApiType.NVUE)

    # Create system admin user and connect
    system_admin, system_admin_pass = add_user_with_system_admin(engines, 'system_admin')

    # Create and connect with users 1-3, each with i sessions
    credentials = []
    for i in range(1, 4):
        username = f'user{i}'
        user, password = create_user(system, username)
        credentials.append((i, user, password))
    NvueGeneralCli.apply_config(engines.dut)

    create_session_thread(engines, system_admin, system_admin_pass)

    # Create sessions using threading
    for i, username, password in credentials:
        create_sessions(engines, username, password, i)

    # Wait for all threads to complete and get the actual session objects
    wait_for_sessions_threads()
    user_sessions = []
    for i, username, _ in credentials:
        user_sessions.extend(sessions_dict[username])

    resest_channels()

    rotate_logs(engines)

    # Disconnect all users in a single command
    disconnect_user(sessions_dict[system_admin][0], retry_run=False)

    # Verify no sessions are active
    verify_sessions_state(engines,
                          users_sessions_should_be_closed=sessions_dict[system_admin] + user_sessions)
    verify_logs_updated_successfully_disconnect_all(engines, [system_admin] + [username for _, username, _ in credentials], [1] + [i for i, _, _ in credentials])


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test04_sudoer_user_disconnect_all(engines):
    """
    Connect with sudo user and disconnect all users

    Procedure:
    1. Create a user with sudo permissions
    2. Create and connect with user1,..., user3, each with i sessions
    3. Connect with sudo user - user1
    4. Disconnect all users
    5. Verify sudoer is disconnected as well as other users
    6. Verify syslog contains:
       - One "session closed" message per user's session
       - One "Successfully disconnected" message per user
    7. Verify nvued log contains:
       - One disconnect operation per user
       - One disconnect message per user
    """
    system = System(force_api=ApiType.NVUE)

    # Create sudo user and connect
    sudo_user, sudo_pass = add_user_with_sudo(engines, 'super')

    # Create and connect with users 1-4, each with i sessions
    credentials = []
    for i in range(1, 5):
        username = f'user{i}'
        user, password = create_user(system, username)
        credentials.append((i, user, password))
    NvueGeneralCli.apply_config(engines.dut)

    create_session_thread(engines, sudo_user, sudo_pass)

    # Create sessions using threading
    for i, username, password in credentials:
        create_sessions(engines, username, password, i)

    # Wait for all threads to complete and get the actual session objects
    wait_for_sessions_threads()
    user_sessions = []
    for i, username, _ in credentials:
        user_sessions.extend(sessions_dict[username])

    resest_channels()

    rotate_logs(engines)

    # Disconnect all users in a single command
    disconnect_user(sessions_dict[sudo_user][0], retry_run=False)

    # Verify no sessions are active
    verify_sessions_state(engines,
                          users_sessions_should_be_closed=sessions_dict[sudo_user] + user_sessions)

    verify_logs_updated_successfully_disconnect_all(engines, [sudo_user] + [username for _, username, _ in credentials], [1] + [i for i, _, _ in credentials])


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test05_user_disconnect_onebyone(engines):
    """
    Connect with system_admin, user with sudo permission - super, and 20 users.
    Use the system_admin user to disconnect user1, ..., user10, one by one.
    Use super to disconnect user11, …, user20, one by one. Verify all session

    Procedure:
    1. Create a user with sudo permissions - super
    2. Create 20 users - user1, user2, user3, …, user20
    3. Start a single session with every user{2k+1}
    4. Start two sessions with every user{2k}
    5. Use system_admin to disconnect user1, …, user10 one by one
    6. Verify no open sessions for user1, ..., user10
    7. Use super to disconnect user11, …, user20 one by one
    8. Verify no open sessions for user11, ..., user20
    9. Verify syslog contains:
       - One "session closed" message per user's session
       - One "Successfully disconnected" message per user
    10. Verify nvued log contains:
       - One disconnect operation per user
       - One disconnect message per user
    """
    system = System(force_api=ApiType.NVUE)

    # Create system admin and super user
    system_admin, system_admin_pass = add_user_with_system_admin(engines, 'system_admin')
    super_user, super_pass = add_user_with_sudo(engines, 'super')

    # Create and connect with 20 users
    credentials = []
    num_users = 20
    for i in range(1, num_users):
        username = f'user{i}_'
        user, password = create_user(system, username)
        credentials.append((1 if i % 2 else 2, user, password))
    NvueGeneralCli.apply_config(engines.dut)

    # Create sessions for system_admin and super using threading
    create_session_thread(engines, system_admin, system_admin_pass)
    create_session_thread(engines, super_user, super_pass)

    # Create sessions using threading
    for session_count, username, password in credentials:
        # Create 1 session for odd users, 2 sessions for even users
        create_sessions(engines, username, password, session_count)
        time.sleep(SESSIONS_DELAY)

    # Wait for all threads to complete and get the actual session objects
    wait_for_sessions_threads()

    # Get all user sessions
    user_sessions = []
    for i, username, _ in credentials:
        user_sessions.extend(sessions_dict[username])

    resest_channels()

    rotate_logs(engines)

    # System admin disconnects users 1-num_users // 2
    for i, username, _ in credentials[:num_users // 2]:
        disconnect_user(sessions_dict[system_admin][0], username)
        verify_sessions_state(engines,
                              users_sessions_should_be_closed=sessions_dict[username])

    # Super disconnects users num_users // 2 - num_users
    for i, username, _ in credentials[num_users // 2:]:
        disconnect_user(sessions_dict[super_user][0], username)
        verify_sessions_state(engines,
                              users_sessions_should_be_closed=sessions_dict[username])

    verify_logs_updated_successfully(engines, [username for _, username, _ in credentials], [session_count for session_count, _, _ in credentials])

    # Clean up
    sessions_dict[system_admin][0].disconnect()
    sessions_dict[super_user][0].disconnect()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test06_negative_unprivileged_disconnect(engines):
    """
    Create an unprivileged user, open a session for him.
    Create 3 users, one unprivileged with one session, second unprivileged with two sessions, third sudo user.
    Create a session with a system_admin user.
    Try to disconnect them one by one, verify no session was closed. Try to disconnect them all, verify no session was closed.

    Procedure:
    1. Create a user with basic permission simple_user
    2. Create 3 users, user1, user2, user3 (with sudo permissions)
    3. Create 1,2,1 sessions accordingly to user1, user2 and user3. Start a session with system_admin
    4. Disconnect user1, verify error not closed
    5. Disconnect user2, verify error not closed
    6. Disconnect user3, verify not closed
    7. Disconnect system_admin, verify error not closed
    8. Try to disconnect all users, verify error, not closed
    9. Verify syslog doesn't contain disconnect attempts
    10. Verify nvued log contains insufficient privileges messages
    """
    system = System(force_api=ApiType.NVUE)

    # Create unprivileged user and connect
    simple_user, simple_pass = create_user(system, 'simple_user')

    # Create other users
    user1, pass1 = create_user(system, 'user1')
    user2, pass2 = create_user(system, 'user2')
    user3, pass3 = create_user(system, 'user3')
    system_admin, system_admin_pass = add_user_with_system_admin(engines, 'system_admin', apply=True)

    # Create sessions using threading
    create_session_thread(engines, simple_user, simple_pass)
    create_session_thread(engines, user1, pass1)
    create_sessions(engines, user2, pass2, 2)
    create_session_thread(engines, user3, pass3)
    create_session_thread(engines, system_admin, system_admin_pass)

    # Wait for all threads to complete and get the actual session objects
    wait_for_sessions_threads()
    simple_session = sessions_dict[simple_user][0]

    resest_channels()

    rotate_logs(engines)

    # Try to disconnect simple_user from simple_session (should fail)
    disconnect_result = disconnect_user(simple_session, simple_user, force_foreground=True)
    assert "Failure" in disconnect_result, f"Expected 'Failure' in disconnect result, got {disconnect_result}"

    # Try to disconnect users from simple_user session (should fail)
    for user in [user1, user2, user3, system_admin]:
        disconnect_result = disconnect_user(simple_session, user)
        assert "Failure" in disconnect_result, f"Expected 'Failure' in disconnect result, got {disconnect_result}"

    # Try to disconnect all users (should fail)
    disconnect_result = disconnect_user(simple_session, force_foreground=True)
    assert "Failure" in disconnect_result, f"Expected 'Failure' in disconnect result, got {disconnect_result}"

    # Verify all sessions are still active
    sessions_should_be_active = sessions_dict[user1] + sessions_dict[user2] + sessions_dict[user3] + sessions_dict[system_admin] + sessions_dict[simple_user]
    verify_sessions_state(engines,
                          users_sessions_should_be_active=sessions_should_be_active)

    verify_logs_updated_successfully(engines, [simple_user, user1, user2, user3, system_admin], expected_msg_counts_for_users=[1, 1, 2, 1, 1], negative=True, negative_user=simple_user)

    for session in sessions_should_be_active:
        session.disconnect()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test07_new_priviliged_group_disconnect(engines):
    """
    Create a role with sufficient permissions to disconnect.
    Create a user with this role try to disconnect another user with the role, system_admin, base, sudoer.
    Disconnect all.

    Procedure:
    1. Create a new group with sudo permissions
    2. Create three users from this group user1, user2 and one session for each, user3 with 2 sessions
    3. Create a basic_user, one session. Create simple1, simple2, simple3, i sessions for each
    4. Create a sudoer user, one session - super
    5. Start a system_admin session
    6. Connect to user1 session and disconnect user2, user3, system_admin, sudoer, basic_user verify it works
    7. Disconnect all, verify simple1, simple2, simple3 and user1 sessions are closed
    8. Verify syslog contains:
       - One "session closed" message per user's session
       - One "Successfully disconnected" message per user
    8. Verify nvued log contains:
       - One disconnect operation per user
       - One disconnect message per user
    """
    system = System(force_api=ApiType.NVUE)

    # Create privileged group and users

    # Create a new RBAC class with specific permissions
    system.aaa.class_rbac.set_new_class("PrivilegedClass", RbacConsts.ALLOW, "/system", RbacConsts.ALL)

    # Create a new role with that class
    system.aaa.role.set_new_role("PrivilegedRole", "PrivilegedClass")

    # Add specific groups (like sudo) to the role
    system.aaa.role.role_id["PrivilegedRole"].class_rbac.class_rbac_id["sudo"].set(apply=True)

    # Create users in privileged group
    user1, pass1 = system.aaa.user.set_new_user(username='user1',
                                                role="PrivilegedRole")
    user2, pass2 = system.aaa.user.set_new_user(username='user2',
                                                role="PrivilegedRole")
    user3, pass3 = system.aaa.user.set_new_user(username='user3',
                                                role="PrivilegedRole",
                                                apply=True)

    # Create other users
    basic_user, basic_pass = create_user(system, 'basic_user')
    simple1, simple_pass1 = create_user(system, 'simple1')
    simple2, simple_pass2 = create_user(system, 'simple2')
    simple3, simple_pass3 = create_user(system, 'simple3')
    system_admin, system_admin_pass = add_user_with_system_admin(engines, 'system_admin')
    super_user, super_pass = add_user_with_sudo(engines, 'super')

    # Create sessions using threading
    create_session_thread(engines, user1, pass1)
    create_session_thread(engines, user2, pass2)
    create_sessions(engines, user3, pass3, 2)
    create_session_thread(engines, basic_user, basic_pass)
    create_session_thread(engines, system_admin, system_admin_pass)
    create_session_thread(engines, super_user, super_pass)

    # Create i sessions for each simple user
    for i, (username, password) in enumerate([(simple1, simple_pass1), (simple2, simple_pass2), (simple3, simple_pass3)], 1):
        create_sessions(engines, username, password, i)

    # Wait for all threads to complete and get the actual session objects
    wait_for_sessions_threads()
    user1_session = sessions_dict[user1][0]

    resest_channels()

    rotate_logs(engines)

    # Disconnect users from user1 session
    disconnect_user(user1_session, user2)
    disconnect_user(user1_session, user3)
    disconnect_user(user1_session, system_admin)
    disconnect_user(user1_session, super_user)
    disconnect_user(user1_session, basic_user)

    verify_sessions_state(engines,
                          users_sessions_should_be_active=sessions_dict[user1] + sessions_dict[simple1] + sessions_dict[simple2] + sessions_dict[simple3],
                          users_sessions_should_be_closed=sessions_dict[user2] + sessions_dict[basic_user] + sessions_dict[super_user] + sessions_dict[system_admin] + sessions_dict[user3])

    verify_logs_updated_successfully(engines, [user2, user3, system_admin, super_user, basic_user], [1, 2, 1, 1, 1])

    # Disconnect all users
    disconnect_user(user1_session, retry_run=False)

    # Verify all sessions are closed
    verify_sessions_state(engines,
                          users_sessions_should_be_closed=sessions_dict[user1] + sessions_dict[user2] + sessions_dict[user3] + sessions_dict[basic_user] + sessions_dict[simple1] + sessions_dict[simple2] + sessions_dict[simple3] + sessions_dict[super_user] + sessions_dict[system_admin])

    verify_logs_updated_successfully_disconnect_all(engines, [user1, simple1, simple2, simple3], expected_msg_counts_for_users=[1, 1, 2, 3])

    # Clean up
    user1_session.disconnect()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test08_new_unprivileged_group_disconnect(engines):
    """
    Create a group with insufficient permissions to disconnect.
    Create a user from this group try to disconnect another user from the group, system_admin, base, sudoer.
    Disconnect all.

    Procedure:
    1. Remove permission from group - no sudo permissions
    2. Create three users from this group user1, user2 and one session for each, user3 with 2 sessions
    3. Create a basic_user, one session. Create simple1, simple2, simple3, i sessions for each
    4. Create a sudoer user, one session - super
    5. Start a system_admin session
    6. Connect to user1 session and disconnect user2, user3, system_admin, sudoer, basic_user verify error occurs
    7. Disconnect all, verify no sessions are closed
    8. Verify syslog doesn't contain disconnect attempts
    9. Verify nvued log contains insufficient privileges messages
    """
    system = System(force_api=ApiType.NVUE)

    # Create unprivileged group and users :

    # Create a new RBAC class with specific permissions
    system.aaa.class_rbac.set_new_class("UnprivilegedClass", RbacConsts.ALLOW, "/system", RbacConsts.ALL)

    # Create a new role with that class
    system.aaa.role.set_new_role("UnprivilegedRole", "UnprivilegedClass", apply=True)

    # Create users in unprivileged group
    user1, pass1 = system.aaa.user.set_new_user(username='user1',
                                                role="UnprivilegedRole")
    user2, pass2 = system.aaa.user.set_new_user(username='user2',
                                                role="UnprivilegedRole")
    user3, pass3 = system.aaa.user.set_new_user(username='user3',
                                                role="UnprivilegedRole")

    # Create other users
    basic_user, basic_pass = create_user(system, 'basic_user')
    simple1, simple_pass1 = create_user(system, 'simple1')
    simple2, simple_pass2 = create_user(system, 'simple2')
    simple3, simple_pass3 = create_user(system, 'simple3')
    system_admin, system_admin_pass = add_user_with_system_admin(engines, 'system_admin')
    super_user, super_pass = add_user_with_sudo(engines, 'super')

    # Create sessions using threading
    create_session_thread(engines, user1, pass1)
    create_session_thread(engines, user2, pass2)
    create_sessions(engines, user3, pass3, 2)
    create_session_thread(engines, basic_user, basic_pass)
    create_session_thread(engines, super_user, super_pass)
    create_session_thread(engines, system_admin, system_admin_pass)

    # Create i sessions for each simple user
    for i, (username, password) in enumerate([(simple1, simple_pass1), (simple2, simple_pass2), (simple3, simple_pass3)], 1):
        create_sessions(engines, username, password, i)

    # Wait for all threads to complete and get the actual session objects
    wait_for_sessions_threads()
    user1_session = sessions_dict[user1][0]

    resest_channels()

    rotate_logs(engines)

    # Try to disconnect users from user1 session (should fail)
    for user in [user2, user3, system_admin, super_user, basic_user]:
        disconnect_result = disconnect_user(user1_session, user)
        assert "Failure" in disconnect_result, f"Expected 'Failure' in disconnect result, got {disconnect_result}"

    # Try to disconnect all users (should fail)
    disconnect_result = disconnect_user(user1_session, force_foreground=True, retry_run=False)
    assert "Failure" in disconnect_result, f"Expected 'Failure' in disconnect result, got {disconnect_result}"

    # Verify all sessions are still active
    sessions_should_be_active = sessions_dict[user1] + sessions_dict[user2] + sessions_dict[user3] + sessions_dict[basic_user] + sessions_dict[simple1] + sessions_dict[simple2] + sessions_dict[simple3] + sessions_dict[super_user] + sessions_dict[system_admin]
    verify_sessions_state(engines,
                          users_sessions_should_be_active=sessions_should_be_active)

    verify_syslog_updated_successfully(engines, [user2, user3, system_admin, super_user, basic_user], [1, 2, 1, 1, 1], action_disconnect_should_fail=True)
    # TODO: fix this after NVUE message is fixed

    # Clean up
    for session in sessions_should_be_active:
        session.disconnect()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test09_negative_user_disconnect_not_exist_not_connected_irregular(engines):
    """
    Create a user with sudo permissions - super, open a session with super, open a session with system_admin.
    Create a user with no open sessions - basic_user.
    Try to disconnect basic_user, try to disconnect invalid_user.
    Verify errors.

    Procedure:
    1. Create user with sudo permissions - super
    2. Create a user basic_user
    3. Create a session with super
    4. Create a session with system_admin
    5. Disconnect basic_user from system_admin, verify specific error
    6. Disconnect basic_user from super, verify specific error
    7. Disconnect invalid_user from system_admin, verify specific error
    8. Disconnect invalid_user from super, verify specific error
    9. Disconnect irregular_user from super, verify specific error
    10. Verify syslog doesn't contain disconnect messages
    11. Verify nvued log contains specific error messages for non-existent and non-logged-in users
    """
    system = System(force_api=ApiType.NVUE)

    # Create users
    system_admin, system_admin_pass = add_user_with_system_admin(engines, 'system_admin')
    basic_user, basic_pass = create_user(system, 'basic_user')
    super_user, super_pass = add_user_with_sudo(engines, 'super')

    # Create sessions using threading
    create_session_thread(engines, super_user, super_pass)
    create_session_thread(engines, system_admin, system_admin_pass)

    # Wait for all threads to complete and get the actual session objects
    wait_for_sessions_threads()
    super_session = sessions_dict[super_user][0]
    system_admin_session = sessions_dict[system_admin][0]

    resest_channels()

    rotate_logs(engines)

    # Try to disconnect non-connected user, non-existent user, irregular user
    irregular_user = "a1A" * 2 + "C_--_-_a" + "b8a" * 6

    for user, message in zip([basic_user, "invalid_user", irregular_user], [NOT_LOGGED_IN_ERROR_MSG, NOT_EXIST_ERROR_MSG, NOT_EXIST_ERROR_MSG]):
        for session in [system_admin_session, super_session]:
            disconnect_result = disconnect_user(session, user)
            assert f"{message % user}" in disconnect_result, f"Expected '{message % user}' error"

    # Verify syslog updates - should not contain disconnect attempts
    with allure.step('Verify syslog updates'):
        new_syslog_entries = cli_common.read_file('/var/log/syslog', is_sudo=True)
        # Verify no disconnect commands are logged
        for user in [basic_user, "invalid_user", irregular_user]:
            assert f"SIGKILL -u {user}" not in new_syslog_entries, f"Syslog should not contain disconnect command for user {user}"
            assert f"session closed for user {user}" not in new_syslog_entries, f"Syslog should not contain session closed message for user {user}"

    # Verify nvued log updates - should contain specific error messages
    with allure.step('Verify nvued log updates'):
        new_nvued_entries = cli_common.read_file('/var/log/nvued.log', is_sudo=True)

        # Verify error for non-existent user, irregular user
        for user in ["invalid_user", irregular_user]:
            assert f"{NOT_EXIST_ERROR_MSG % user}" in new_nvued_entries, f"nvued log should contain error for non-existent user: {NOT_EXIST_ERROR_MSG % user}"

        # Verify error for non-logged-in user
        assert f"{NOT_LOGGED_IN_ERROR_MSG % basic_user}" in new_nvued_entries, f"nvued log should contain error for non-logged-in user: {NOT_LOGGED_IN_ERROR_MSG % basic_user}"

    # Clean up
    super_session.disconnect()
    system_admin_session.disconnect()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test10_disconnect_users_with_30_sessions(engines, change_ssh):
    """
    Create a sudo user - super.
    Create two basic users, each with 30 session, and try to disconnect them, from system_admin and super.

    Procedure:
    1. Create a sudo user - super
    2. Create two basic users - user1, user2
    3. Start 30 sessions for user1, user2 using threading
    4. Disconnect user1 using super, verify all user1's sessions are closed
    5. Disconnect user2 using system_admin, verify all user2's sessions are closed
    6. Verify syslog contains disconnect messages for both users
    7. Verify nvued log contains disconnect messages for both users
    """
    system = System(force_api=ApiType.NVUE)

    # Create users
    user1, pass1 = create_user(system, 'user1')
    user2, pass2 = create_user(system, 'user2')
    system_admin, system_admin_pass = add_user_with_system_admin(engines, 'system_admin')
    super_user, super_pass = add_user_with_sudo(engines, 'super')

    # Create sessions using threading
    create_session_thread(engines, super_user, super_pass)
    create_session_thread(engines, system_admin, system_admin_pass)

    # Create 30 sessions for each user using threading
    num_sessions = 30
    create_sessions(engines, user1, pass1, num_sessions, port=NEW_SSH_PORT1, sleep=SESSIONS_DELAY)
    create_sessions(engines, user2, pass2, num_sessions, port=NEW_SSH_PORT2, sleep=SESSIONS_DELAY)

    # Wait for all threads to complete
    wait_for_sessions_threads()
    num_sessions1, num_sessions2 = len(sessions_dict[user1]), len(sessions_dict[user2])
    resest_channels()

    rotate_logs(engines)

    # Disconnect users
    disconnect_user(sessions_dict[super_user][0], user1)
    disconnect_user(sessions_dict[system_admin][0], user2)

    # Verify all sessions are closed
    verify_sessions_disconnected(engines, user1)
    verify_sessions_disconnected(engines, user2)

    verify_syslog_updated_successfully(engines, [user1, user2], [num_sessions1, num_sessions2])

    # Clean up
    sessions_dict[super_user][0].disconnect()
    sessions_dict[system_admin][0].disconnect()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test11_system_admin_disconnect_14(engines, change_ssh):
    """
    Create 14 users with one/two sessions each.
    Disconnect half of the users one by one.
    Verify sessions not open.
    Disconnect all left.
    Verify no sessions open.

    Procedure:
    1. Create 14 users, start 1/2 session for each using threading
    2. Disconnect user1,…, user7 one by one, verify closed
    3. Disconnect all
    4. Verify all closed
    5. Verify syslog contains disconnect messages for all users
    6. Verify nvued log contains disconnect messages for all users
    """
    system = System(force_api=ApiType.NVUE)
    all_sessions = []

    # Create system admin user
    system_admin, system_admin_pass = add_user_with_system_admin(engines, 'system_admin')

    # Create 14 users with one/two sessions each using threading
    user_credentials = []
    num_users = 14
    for i in range(1, num_users + 1):
        username = f'user{i}_'
        user, password = create_user(system, username, apply=False)
        user_credentials.append((username, password, 2 - (i % 2)))

    NvueGeneralCli.apply_config(engines.dut)

    create_session_thread(engines, system_admin, system_admin_pass)

    # Create sessions using threading
    for idx, (username, password, num_sessions) in enumerate(user_credentials):
        create_sessions(engines, username, password, num_sessions, port=NEW_SSH_PORT1 if idx < num_users // 2 else NEW_SSH_PORT2, sleep=SESSIONS_DELAY)
        time.sleep(SESSIONS_DELAY)

    # Wait for all threads to complete
    wait_for_sessions_threads()

    resest_channels()

    rotate_logs(engines)

    all_sessions.append(sessions_dict[system_admin][0])

    # Get the actual session objects
    for username, _, num_sessions in user_credentials:
        all_sessions.extend(sessions_dict[username])

    # Disconnect first 20 users one by one
    for username, _, _ in user_credentials[:num_users // 2]:
        disconnect_user(sessions_dict[system_admin][0], username)

    for username, _, _ in user_credentials[:num_users // 2]:
        verify_sessions_disconnected(engines, username)

    verify_logs_updated_successfully(engines, [user for user, _, _ in user_credentials[:num_users // 2]], [num_sessions for _, _, num_sessions in user_credentials[:num_users // 2]])

    # Disconnect all remaining users
    disconnect_user(sessions_dict[system_admin][0], retry_run=False)

    for username, _, _ in user_credentials[num_users // 2:]:
        verify_sessions_disconnected(engines, username)

    verify_logs_updated_successfully_disconnect_all(engines, [user for user, _, _ in user_credentials[num_users // 2:]] + [system_admin], [num_sessions for _, _, num_sessions in user_credentials[num_users // 2:]] + [1])


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test12_super_disconnect_14(engines, change_ssh):
    """
    Create sudo user - super.
    Create 14 users with one/two sessions each.
    Disconnect half of the users one by one.
    Verify sessions not open.
    Disconnect all left.
    Verify no sessions open.

    Procedure:
    1. Create a sudo user - super, one session
    2. Create 14 users, start 1/2 session for each using threading
    3. Disconnect user1,…, user7 one by one, verify closed
    4. Disconnect all
    5. Verify all closed
    6. Verify syslog contains disconnect messages for all users
    7. Verify nvued log contains disconnect messages for all users
    """
    system = System(force_api=ApiType.NVUE)

    # Create super user
    super_user, super_pass = add_user_with_sudo(engines, 'super')
    create_session_thread(engines, super_user, super_pass)

    # Create 14 users with one/two sessions each using threading
    num_users = 14
    user_credentials = []
    for i in range(1, num_users + 1):
        username = f'user{i}_'
        user, password = create_user(system, username, apply=False)
        user_credentials.append((username, password, 2 - (i % 2)))

    NvueGeneralCli.apply_config(engines.dut)

    # Create sessions using threading
    for idx, (username, password, num_sessions) in enumerate(user_credentials):
        create_sessions(engines, username, password, num_sessions, port=NEW_SSH_PORT1 if idx < num_users // 2 else NEW_SSH_PORT2, sleep=SESSIONS_DELAY)
        time.sleep(SESSIONS_DELAY)

    # Wait for all threads to complete
    wait_for_sessions_threads()

    resest_channels()

    rotate_logs(engines)

    # Get the actual session objects
    all_sessions = sessions_dict[super_user]
    for username, _, num_sessions in user_credentials:
        all_sessions.extend(sessions_dict[username])

    # Disconnect first 20 users one by one
    for username, _, _ in user_credentials[:num_users // 2]:
        disconnect_user(sessions_dict[super_user][0], username)
        verify_sessions_disconnected(engines, username)

    verify_syslog_updated_successfully(engines, [user for user, _, _ in user_credentials[:num_users // 2]], [num_sessions for _, _, num_sessions in user_credentials[:num_users // 2]])

    disconnect_user(sessions_dict[super_user][0], retry_run=False)

    verify_logs_updated_successfully_disconnect_all(engines, [user for user, _, _ in user_credentials[num_users // 2:]] + [super_user], [num_sessions for _, _, num_sessions in user_credentials[num_users // 2:]] + [1])


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test13_edge_user_disconnect(engines):
    """
    Create a super user - sudo permissions.
    Create two users with max chars and special chars, one session each.
    Disconnect one by super, disconnect one by system_admin.

    Procedure:
    1. Create a sudo user - super
    2. Create two basic users - user1_long_name, user2_long_name
    3. Disconnect user1 using super, verify all user1's sessions are closed
    4. Disconnect user2 using system_admin, verify all user2's sessions are closed
    5. Verify syslog contains disconnect messages for both users
    6. Verify nvued log contains disconnect messages for both users
    """
    system = System(force_api=ApiType.NVUE)

    # Create users with edge cases
    system_admin, system_admin_pass = add_user_with_system_admin(engines, 'system_admin')
    super_user, super_pass = add_user_with_sudo(engines, 'super')

    # Create users with long names and special characters
    user1 = 'u1' + 'a2-' * 10
    user2 = 'u2' + '2-N' * 10

    user1, pass1 = create_user(system, user1)
    user2, pass2 = create_user(system, user2, apply=True)

    # Create sessions using threading
    create_session_thread(engines, super_user, super_pass)
    create_session_thread(engines, system_admin, system_admin_pass)
    create_session_thread(engines, user1, pass1)
    create_session_thread(engines, user2, pass2)

    # Wait for all threads to complete and get the actual session objects
    wait_for_sessions_threads()

    resest_channels()

    rotate_logs(engines)

    # Disconnect users
    disconnect_user(sessions_dict[super_user][0], user1)
    disconnect_user(sessions_dict[system_admin][0], user2)

    # Verify sessions are closed
    verify_sessions_disconnected(engines, user1)
    verify_sessions_disconnected(engines, user2)

    verify_syslog_updated_successfully(engines, [user1, user2], [1, 1])

    # Clean up
    sessions_dict[super_user][0].disconnect()
    sessions_dict[system_admin][0].disconnect()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test14_disconnect_user_from_two_users(engines):
    """
    Create two sudo users and try to disconnect same user with open session.
    Verify error for the second.

    Procedure:
    1. Create two sudo users - super1, super2
    2. Create a user with one session
    3. Disconnect user using super1
    4. Disconnect user using super2
    5. Verify error for super 2
    6. Verify syslog contains:
       - One "session closed" message for the target user
       - One "Successfully disconnected" message for the target user
    7. Verify nvued log contains:
       - One disconnect operation for the target user
       - One disconnect message for the target user
       - One "not logged in" error message for the second disconnect attempt
    """
    system = System(force_api=ApiType.NVUE)

    # Create target user
    target_user, target_pass = create_user(system, 'target_user')

    # Create sudo users
    super1, pass1 = add_user_with_sudo(engines, 'super1')
    super2, pass2 = add_user_with_sudo(engines, 'super2')

    # Create sessions using threading
    create_session_thread(engines, super1, pass1)
    create_session_thread(engines, super2, pass2)
    create_session_thread(engines, target_user, target_pass)

    # Wait for all threads to complete and get the actual session objects
    wait_for_sessions_threads()

    resest_channels()

    rotate_logs(engines)

    # First disconnect should succeed
    disconnect_user(sessions_dict[super1][0], target_user)
    verify_sessions_disconnected(engines, target_user)

    # Second disconnect should fail
    disconnect_result = disconnect_user(sessions_dict[super2][0], target_user)
    assert "Failure" in disconnect_result, f"Expected 'Failure' in disconnect result, got {disconnect_result}"
    assert NOT_LOGGED_IN_ERROR_MSG % target_user in disconnect_result, f"Expected '{NOT_LOGGED_IN_ERROR_MSG % target_user}' error"

    # Verify syslog updates
    with allure.step('Verify syslog updates'):
        new_syslog_entries = cli_common.read_file('/var/log/syslog', is_sudo=True)
        # Verify disconnect command is logged for the target user
        assert f"SIGKILL -u {target_user}" in new_syslog_entries, f"Syslog should contain disconnect command for user {target_user}"
        assert f"session closed for user {target_user}" in new_syslog_entries, f"Syslog should contain session closed message for user {target_user}"

    # Verify nvued log updates
    with allure.step('Verify nvued log updates'):
        new_nvued_entries = cli_common.read_file('/var/log/nvued.log', is_sudo=True)
        # Verify successful disconnect operation
        assert f"running ActionKey('@disconnect', '/system/aaa/user/{{user-id}}', ('{target_user}'" in new_nvued_entries, f"nvued log should contain disconnect operation for user {target_user}"
        # assert f'nv action disconnect system aaa user {target_user}' in new_nvued_entries, f"nvued log should contain disconnect message for user {target_user} by NVUE"

        # Verify "not logged in" error message for the second disconnect attempt
        assert NOT_LOGGED_IN_ERROR_MSG % target_user in new_nvued_entries, f"nvued log should contain error for non-logged-in user: {NOT_LOGGED_IN_ERROR_MSG % target_user}"
    # Clean up
    sessions_dict[super1][0].disconnect()
    sessions_dict[super2][0].disconnect()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test15_rest_api_disconnect_users(engines):
    """
    Verify that a user with sudo permissions can disconnect other users, including another sudo user,
    a system_admin, and basic users, and can disconnect all users.

    Procedure:
    1. Verify Nginx runs
    2. Create a user with sudo permissions (e.g., super).
    3. Create another sudo user (e.g., sudo_user).
    4. Create a system_admin user.
    5. Create four basic users (e.g., user1, user2, user3, user4).
    6. Start two sessions for user1 and user2.
    7. Start one session for user3 and user4.
    8. Use the REST API to disconnect sudo_user using super.
    9. Use the REST API to disconnect system_admin using super.
    10. Use the REST API to disconnect user3 (single session) using super.
    11. Use the REST API to disconnect user1 (two sessions) using super.
    12. Use the REST API to disconnect all users using super.
    13. Verify that the appropriate response is received after each action.
    14. Verify syslog is updated with commands results.
    """
    # Use NVUE API for user creation and session management
    system = System(force_api=ApiType.NVUE)

    run_nginx(engines)

    # Create system admin user
    system_admin, system_admin_pass = add_user_with_system_admin(engines, 'system_admin')
    # Create users with sudo permissions
    super_user, super_pass = add_user_with_sudo(engines, 'super')
    sudo_user, sudo_pass = add_user_with_sudo(engines, 'sudo_user')

    # Create basic users
    user1, pass1 = create_user(system, 'user1')
    user2, pass2 = create_user(system, 'user2')
    user3, pass3 = create_user(system, 'user3')
    user4, pass4 = create_user(system, 'user4', apply=True)

    # Create sessions using threading
    create_session_thread(engines, super_user, super_pass)
    create_session_thread(engines, sudo_user, sudo_pass)
    create_session_thread(engines, system_admin, system_admin_pass)

    # Create two sessions for user1 and user2
    create_sessions(engines, user1, pass1, 2)
    create_sessions(engines, user2, pass2, 2)

    # Create one session for user3 and user4
    create_session_thread(engines, user3, pass3)
    create_session_thread(engines, user4, pass4)

    # Wait for all threads to complete
    wait_for_sessions_threads()

    resest_channels()

    rotate_logs(engines)

    # Use REST API to disconnect users
    with allure.step('Disconnect sudo_user using REST API'):
        # Disconnect sudo_user
        disconnect_user_open_api(engines, super_user, super_pass, sudo_user)
        verify_sessions_disconnected(engines, sudo_user)

    with allure.step('Disconnect system_admin using REST API'):
        # Disconnect system_admin
        disconnect_user_open_api(engines, super_user, super_pass, system_admin)
        verify_sessions_disconnected(engines, system_admin)

    with allure.step('Disconnect user1 (two sessions) using REST API'):
        # Disconnect user1
        disconnect_user_open_api(engines, super_user, super_pass, user1)
        verify_sessions_disconnected(engines, user1)

    with allure.step('Disconnect user3 (single session) using REST API'):
        # Disconnect user3
        disconnect_user_open_api(engines, super_user, super_pass, user3)
        verify_sessions_disconnected(engines, user3)

    verify_logs_updated_successfully(engines, [user1, user3, sudo_user, system_admin], [2, 1, 1, 1])

    with allure.step('Disconnect all users using OPEN API'):
        # Disconnect all users
        response = disconnect_user_open_api(engines, super_user, super_pass)
        if "All users have been logged out" not in response:
            logger.warning("A correct response was not received")

    verify_sessions_state(engines, users_sessions_should_be_closed=sessions_dict[user2] + sessions_dict[user4] + sessions_dict[super_user])
    verify_logs_updated_successfully_disconnect_all(engines, [user2, user4, super_user], [2, 1, 1])

    sessions_dict[super_user][0].disconnect()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test16_system_admin_rest_api_disconnect_users(engines):
    """
    Verify that a system_admin can disconnect other users, including a sudo user, and basic users,
    and can disconnect all users.

    Procedure:
    1. Verify Nginx runs
    2. Create a system_admin user (e.g., system_admin1).
    3. Create another system_admin user (e.g., system_admin2).
    4. Create a user with sudo permissions (e.g., sudo_user).
    5. Create four basic users (e.g., user1, user2, user3, user4).
    6. Start two sessions for user1 and user2.
    7. Start one session for user3 and user4.
    8. Use the REST API to disconnect system_admin2 using system_admin1.
    9. Use the REST API to disconnect sudo_user using system_admin1.
    10. Use the REST API to disconnect user3 (single session) using system_admin1.
    11. Use the REST API to disconnect user1 (two sessions) using system_admin1.
    12. Use the REST API to disconnect all users using system_admin1.
    13. Verify that the appropriate response is received after each action.
    14. Verify syslog is updated with commands results.
    """
    # Use NVUE API for user creation and session management
    system = System(force_api=ApiType.NVUE)

    run_nginx(engines)

    # Create system admin users
    system_admin1, system_admin1_pass = add_user_with_system_admin(engines, 'system_admin1')
    system_admin2, system_admin2_pass = add_user_with_system_admin(engines, 'system_admin2')

    # Create sudo user
    sudo_user, sudo_pass = add_user_with_sudo(engines, 'sudo_user')

    # Create basic users
    user1, pass1 = create_user(system, 'user1')
    user2, pass2 = create_user(system, 'user2')
    user3, pass3 = create_user(system, 'user3')
    user4, pass4 = create_user(system, 'user4', apply=True)

    # Create sessions using threading
    create_session_thread(engines, system_admin1, system_admin1_pass)
    create_session_thread(engines, system_admin2, system_admin2_pass)
    create_session_thread(engines, sudo_user, sudo_pass)

    # Create two sessions for user1 and user2
    create_sessions(engines, user1, pass1, 2)
    create_sessions(engines, user2, pass2, 2)

    # Create one session for user3 and user4
    create_session_thread(engines, user3, pass3)
    create_session_thread(engines, user4, pass4)

    # Wait for all threads to complete
    wait_for_sessions_threads()

    resest_channels()

    rotate_logs(engines)

    # Use REST API to disconnect users
    with allure.step('Disconnect system_admin2 using REST API'):
        # Disconnect system_admin2
        disconnect_user_open_api(engines, system_admin1, system_admin1_pass, system_admin2)
        verify_sessions_disconnected(engines, system_admin2)

    with allure.step('Disconnect sudo_user using REST API'):
        # Disconnect sudo_user
        disconnect_user_open_api(engines, system_admin1, system_admin1_pass, sudo_user)
        verify_sessions_disconnected(engines, sudo_user)

    with allure.step('Disconnect user1 (two sessions) using REST API'):
        # Disconnect user1
        disconnect_user_open_api(engines, system_admin1, system_admin1_pass, user1)
        verify_sessions_disconnected(engines, user1)

    with allure.step('Disconnect user3 (single session) using REST API'):
        # Disconnect user3
        disconnect_user_open_api(engines, system_admin1, system_admin1_pass, user3)
        verify_sessions_disconnected(engines, user3)

    with allure.step('Disconnect all users using OPEN API'):
        # Disconnect all users
        response = disconnect_user_open_api(engines, system_admin1, system_admin1_pass)
        if "All users have been logged out" not in response:
            logger.warning("A correct response was not received")

    verify_logs_updated_successfully(engines, [user1, user3, sudo_user, system_admin2], [2, 1, 1, 1])
    verify_logs_updated_successfully_disconnect_all(engines, [user2, user4, system_admin2], [2, 1, 1])

    sessions_dict[system_admin1][0].disconnect()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test17_role_based_disconnect_permissions(engines):
    """
    Verify that users from different roles can disconnect others and themselves, and verify the behavior
    of privileged and unprivileged roles.

    Procedure:
    1. Verify Nginx runs
    2. Create a system_admin user and start a session.
    3. Create a user with sudo permissions (e.g., sudo_user) and start a session.
    4. Create a simple user from a simple role (e.g., simple_user) and start a session.
    5. Use the REST API to attempt to disconnect system_admin using simple_user and verify the error.
    6. Use the REST API to attempt to disconnect sudo_user using simple_user and verify the error.
    7. Use the REST API to attempt to disconnect all users using simple_user and verify the error.
    8. Use the REST API to disconnect system_admin from system_admin and verify the session is closed.
    9. Use the REST API to disconnect sudo_user from sudo_user and verify the session is closed.
    10. Create two roles: one with permissions to disconnect users and one without.
    11. Create users from these roles and start sessions.
    12. Use the REST API to attempt to disconnect users from the unprivileged role and verify the error.
    13. Use the REST API to disconnect users from the privileged role and verify the sessions are closed.
    14. Verify syslog is updated with commands results
    """
    # Use NVUE API for user creation and session management
    system = System(force_api=ApiType.NVUE)

    run_nginx(engines)

    # Create system admin user
    system_admin, system_admin_pass = add_user_with_system_admin(engines, 'system_admin')
    # Create simple user
    simple_user, simple_pass = create_user(system, 'simple_user')
    # Create sudo user
    sudo_user, sudo_pass = add_user_with_sudo(engines, 'sudo_user')

    # Create two roles: one with permissions to disconnect users and one without
    with allure.step('Create two roles: one with permissions to disconnect users and one without'):
        # Create a new RBAC class with specific permissions for disconnecting users
        system.aaa.class_rbac.set_new_class("DisconnectClass", RbacConsts.ALLOW, "/system", RbacConsts.ALL)

        # Create a new role with that class
        system.aaa.role.set_new_role("DisconnectRole", "DisconnectClass")

        system.aaa.role.role_id["DisconnectRole"].class_rbac.class_rbac_id["sudo"].set(apply=True)

        # Create a new RBAC class without permissions for disconnecting users
        system.aaa.class_rbac.set_new_class("NoDisconnectClass", RbacConsts.ALLOW, "/system", RbacConsts.ALL)

        # Create a new role with that class
        system.aaa.role.set_new_role("NoDisconnectRole", "NoDisconnectClass", apply=True)

        # Create users from these roles
        privilige_user, privilige_pass = system.aaa.user.set_new_user(username='disconnect_user',
                                                                      role="DisconnectRole")
        no_privilige_user, no_privilige_pass = system.aaa.user.set_new_user(username='no_disconnect_user',
                                                                            role="NoDisconnectRole",
                                                                            apply=True)

    # Create sessions using threading
    create_session_thread(engines, privilige_user, privilige_pass)
    create_session_thread(engines, no_privilige_user, no_privilige_pass)

    # Create sessions using threading
    create_session_thread(engines, system_admin, system_admin_pass)
    create_session_thread(engines, sudo_user, sudo_pass)
    create_session_thread(engines, simple_user, simple_pass)

    # Wait for all threads to complete
    wait_for_sessions_threads()

    resest_channels()

    rotate_logs(engines)

    # Use REST API to attempt to disconnect simple_user, system_admin, sudo_user using simple_user and verify the error
    for user in [simple_user, system_admin, sudo_user]:
        with allure.step(f'Attempt to disconnect {user} using simple_user and verify error'):
            response = disconnect_user_open_api(engines, simple_user, simple_pass, user)
            check_error_message(response)
            verify_sessions_active(engines, user)

    # Use REST API to attempt to disconnect all users using simple_user and verify the error
    with allure.step('Attempt to disconnect all users using simple_user and verify error'):
        response = disconnect_user_open_api(engines, simple_user, simple_pass)
        check_error_message(response)
        verify_sessions_active(engines, simple_user)

    # Use REST API to disconnect system_admin from system_admin and verify the session is closed
    with allure.step('Disconnect system_admin from system_admin and verify session is closed'):
        disconnect_user_open_api(engines, system_admin, system_admin_pass, system_admin)
        verify_sessions_disconnected(engines, system_admin)

    # Use REST API to disconnect sudo_user from sudo_user and verify the session is closed
    with allure.step('Disconnect sudo_user from sudo_user and verify session is closed'):
        disconnect_user_open_api(engines, sudo_user, sudo_pass, sudo_user)
        verify_sessions_disconnected(engines, sudo_user)

    # Use REST API to attempt to disconnect users from the unprivileged role and verify the error
    with allure.step('Attempt to disconnect users from the unprivileged role and verify error'):

        response = disconnect_user_open_api(engines, no_privilige_user, no_privilige_pass, privilige_user)
        check_error_message(response)
        verify_sessions_active(engines, privilige_user)

        response = disconnect_user_open_api(engines, no_privilige_user, no_privilige_pass)
        check_error_message(response)
        verify_sessions_active(engines, privilige_user)

    # Use REST API to disconnect users from the privileged role and verify the sessions are closed
    with allure.step('Disconnect users from the privileged role and verify sessions are closed'):
        for user in [no_privilige_user, simple_user]:
            # Disconnect no_disconnect_user
            disconnect_user_open_api(engines, privilige_user, privilige_pass, user)
            verify_sessions_disconnected(engines, user)

        # Disconnect all users
        disconnect_user_open_api(engines, privilige_user, privilige_pass)
        verify_sessions_disconnected(engines, privilige_user)

    verify_logs_updated_successfully(engines, [system_admin, sudo_user, no_privilige_user, simple_user], [1, 1, 1, 1])
    verify_logs_updated_successfully_disconnect_all(engines, [privilige_user], [1])


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test18_rest_api_disconnect_nginx_down(engines):
    """
    Test negative scenarios for REST API disconnect operations when NGINX service is down.
    Verify proper error handling and consistent error messages across different user roles.

    Steps:
    1. Create users with different privilege levels
    2. Create sessions for all users
    3. Stop NGINX service
    4. Attempt to disconnect users using REST API from different roles
    5. Verify all sessions are still active
    6. Start NGINX service
    7. Verify sessions are still active
    8. Verify logs updates - should not contain disconnect messages
    9. Clean up
    """
    # Create users with different privilege levels
    basic_user, basic_pass = add_user_with_sudo(engines, 'basic_user')
    system_admin, system_admin_pass = add_user_with_system_admin(engines, 'system_admin')
    sudo_user, sudo_pass = add_user_with_sudo(engines, 'sudo_user')

    # Create sessions for all users using threading
    create_session_thread(engines, basic_user, basic_pass)
    create_session_thread(engines, system_admin, system_admin_pass)
    create_session_thread(engines, sudo_user, sudo_pass)

    # Wait for all threads to complete
    wait_for_sessions_threads()

    resest_channels()

    rotate_logs(engines)

    # Stop NGINX service
    with allure.step('Stop NGINX service'):
        engines.dut.run_cmd('sudo systemctl stop nginx')
        time.sleep(2)  # Wait for service to fully stop

    # Attempt to disconnect users using REST API from different roles
    with allure.step('Attempt to disconnect users with NGINX down'):
        # System admin attempts to disconnect basic user
        try:
            response = disconnect_user_open_api(engines, system_admin, system_admin_pass, basic_user)
            logger.warning(f"Unexpected success: {response}")
        except Exception as e:
            logger.warning(f"Expected error for system admin: {str(e)}")
            assert "Connection refused" in str(e) or "Failed to establish a new connection" in str(e), f"Unexpected error: {str(e)}"

        # Sudo user attempts to disconnect basic user
        try:
            response = disconnect_user_open_api(engines, sudo_user, sudo_pass, basic_user)
            logger.warning(f"Unexpected success: {response}")
        except Exception as e:
            logger.warning(f"Expected error for sudo user: {str(e)}")
            assert "Connection refused" in str(e) or "Failed to establish a new connection" in str(e), f"Unexpected error: {str(e)}"

        # Basic user attempts to disconnect another user
        try:
            response = disconnect_user_open_api(engines, basic_user, basic_pass, system_admin)
            logger.warning(f"Unexpected success: {response}")
        except Exception as e:
            logger.warning(f"Expected error for basic user: {str(e)}")
            assert "Connection refused" in str(e) or "Failed to establish a new connection" in str(e), f"Unexpected error: {str(e)}"

        # System admin attempts to disconnect all users
        try:
            response = disconnect_user_open_api(engines, system_admin, system_admin_pass)
            logger.warning(f"Unexpected success: {response}")
        except Exception as e:
            logger.warning(f"Expected error for disconnect all: {str(e)}")
            assert "Connection refused" in str(e) or "Failed to establish a new connection" in str(e), f"Unexpected error: {str(e)}"

    # Verify all sessions are still active
    with allure.step('Verify all sessions remain active'):
        verify_sessions_state(engines,
                              users_sessions_should_be_active=sessions_dict[basic_user] + sessions_dict[system_admin] + sessions_dict[sudo_user])

    # Verify syslog updates - should not contain disconnect messages
    with allure.step('Verify syslog updates'):
        new_syslog_entries = cli_common.read_file('/var/log/syslog', is_sudo=True)
        assert f"SIGKILL -u" not in new_syslog_entries, f"Syslog should not contain disconnect command for user"
        assert f"session closed for user" not in new_syslog_entries, f"Syslog should not contain session closed message for any user"

    run_nginx(engines)

    # Verify sessions are still active after NGINX restart
    with allure.step('Verify sessions remain active after NGINX restart'):
        verify_sessions_state(engines,
                              users_sessions_should_be_active=sessions_dict[basic_user] + sessions_dict[system_admin] + sessions_dict[sudo_user])

    # Clean up
    for session in sessions_dict[basic_user] + sessions_dict[system_admin] + sessions_dict[sudo_user]:
        session.disconnect()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test19_disconnect_user_during_scp_transfer(engines):
    """
    Test disconnecting a user while they are performing an SCP file transfer.
    Verify that the transfer is interrupted and the user is disconnected properly.

    Procedure:
    1. Create a sudo user - super
    2. Create a basic user - scp_user
    3. Create a test file of significant size (e.g., 100MB)
    4. Start an SCP transfer from scp_user to the system using LinuxSshEngine
    5. While transfer is in progress, use super to disconnect scp_user
    6. Verify:
       - User is disconnected
       - SCP transfer is interrupted
    """
    system = System(force_api=ApiType.NVUE)

    # Create users
    scp_user, scp_pass = create_user(system, 'file_transfer_user')
    super_user, super_pass = add_user_with_sudo(engines, 'super')

    # Create sessions
    create_session_thread(engines, scp_user, scp_pass)
    create_session_thread(engines, super_user, super_pass)

    # Wait for all threads to complete and get the actual session objects
    wait_for_sessions_threads()

    # Get session objects
    super_session = sessions_dict[super_user][0]
    scp_session = sessions_dict[scp_user][0]
    add_ssh_key_to_localhost(engines, scp_user)

    resest_channels()

    rotate_logs(engines)

    # Create a large test file (1000MB)
    with allure.step('Create large test file'):
        test_file = '/tmp/large_test_file'
        engines.dut.run_cmd(f'sudo dd if=/dev/zero of={test_file} bs=1M count=1000')
        engines.dut.run_cmd(f'sudo chmod 644 {test_file}')

    # Start SCP transfer in a separate thread
    with allure.step('Start SCP transfer'):
        def scp_transfer():
            try:
                # Use LinuxSshEngine's upload_file_using_scp function
                scp_session.upload_file_using_scp(
                    dest_username=scp_user,
                    dest_password=scp_pass,
                    dest_ip='localhost',
                    local_file_path=test_file,
                    dest_folder=f'/home/{scp_user}/',
                    retries=0
                )
            except Exception as e:
                logger.info(f"SCP transfer interrupted: {str(e)}")

        # Start SCP transfer in a thread
        scp_thread = threading.Thread(target=scp_transfer)
        scp_thread.start()

        # Verify transfer is in progress
        transfer_process = engines.dut.run_cmd('ps aux | grep scp | grep -v grep')
        assert 'scp' in transfer_process, "SCP transfer not started"
        # Disconnect the user while transfer is in progress
        with allure.step('Disconnect user during transfer'):
            disconnect_user(super_session, scp_user)

        # Wait for thread to complete
        scp_thread.join()

        # Verify transfer is no longer running
        transfer_process = engines.dut.run_cmd('ps aux | grep scp | grep -v grep')
        assert 'scp' not in transfer_process, "SCP transfer still running"

        # Verify user is disconnected
        verify_sessions_disconnected(engines, scp_user)

    # Verify logs
    verify_logs_updated_successfully(engines, [scp_user], [2])

    # Clean up
    engines.dut.run_cmd(f'sudo rm -f {test_file}')
    engines.dut.run_cmd(f'sudo rm -f /home/{scp_user}/large_test_file')
    super_session.disconnect()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
def test20_different_connection_types(engines):
    """
    Test disconnecting a user from a serial connection.
    Verify that the session is disconnected properly.
    """
    system = System(force_api=ApiType.NVUE)
    system_admin_user, system_admin_password = add_user_with_system_admin(engines, 'system_admin')
    basic_user1, basic_password1 = create_user(system, 'basic1')
    basic_user2, basic_password2 = create_user(system, 'basic2')
    basic_user3, basic_password3 = create_user(system, 'basic3', apply=True)

    create_session_thread(engines, system_admin_user, system_admin_password)
    create_session_thread(engines, basic_user1, basic_password1)
    create_sessions(engines, basic_user2, basic_password2, 2)
    create_session_thread(engines, basic_user3, basic_password3)
    wait_for_sessions_threads()

    resest_channels()

    rotate_logs(engines)

    with allure.step(f'Open a serial connection and login with {system_admin_user}\'s credentials'):
        topology_obj = TestToolkit.topology_obj
        with allure.step('enter to serial context'):
            serial = SerialConsoleTool.get_serial_console_session(topology_obj)
        with allure.step('exit existing login'):
            SerialConsoleTool.exit_existing_login(serial)
        SerialConsoleTool.login_nos(serial_engine=serial, username=system_admin_user, password=system_admin_password, start_login_tries=10, handle_change_password_prompt=False)
        session = SerialConsoleTool.get_serial_console_session(topology_obj)
        disconnect_user_serial_connection(session, basic_user1, serial_engine=True)
        disconnect_user_serial_connection(session, basic_user2, serial_engine=True)

        verify_sessions_state(engines, users_sessions_should_be_active=sessions_dict[system_admin_user] + sessions_dict[basic_user3], users_sessions_should_be_closed=sessions_dict[basic_user1] + sessions_dict[basic_user2])
        verify_sessions_active(engines, system_admin_user, expected_num_sessions=2)

        disconnect_user_serial_connection(session, system_admin_user, validate=False, serial_engine=True)

        verify_sessions_state(engines, users_sessions_should_be_active=sessions_dict[basic_user3], users_sessions_should_be_closed=sessions_dict[basic_user1] + sessions_dict[basic_user2] + sessions_dict[system_admin_user])
        verify_logs_updated_successfully(engines, [system_admin_user, basic_user1, basic_user2], [2, 1, 2])
        SerialConsoleTool.exit_existing_login(serial)
        SerialConsoleTool.login_nos(serial_engine=serial, username=system_admin_user, password=system_admin_password, start_login_tries=10, handle_change_password_prompt=False)
        session = SerialConsoleTool.get_serial_console_session(topology_obj)
        disconnect_user_serial_connection(session, validate=False, serial_engine=True)

    verify_sessions_state(engines, users_sessions_should_be_active=[], users_sessions_should_be_closed=sessions_dict[basic_user3])
    verify_logs_updated_successfully_disconnect_all(engines, [basic_user3], [1])


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.radius
def test21_disconnect_radius_user(engines):
    """
    Test disconnecting a RADIUS user.
    """
    system = System(force_api=ApiType.NVUE)

    # Create a sudo user
    super_user, super_pass = add_user_with_sudo(engines, 'super')

    # Create a session for the sudo user
    create_session(engines, super_user, super_pass)

    config_radius_server(engines)
    set_radius_order(engines)

    # Create RADIUS user sessions
    radius_users = ["pradadm1", "pradmon1"]
    radius_passwords = ["pradadm1", "pradmon1"]

    # Create sessions for RADIUS users
    for user, password in zip(radius_users, radius_passwords):
        create_session_thread(engines, user, password)

    # Wait for all threads to complete
    wait_for_sessions_threads()

    # Reset channels and logs
    resest_channels()
    rotate_logs(engines)

    # Verify the sessions are active
    for user in radius_users:
        verify_sessions_active(engines, user, expected_num_sessions=1)

    # Disconnect the RADIUS users using sudo user
    for user in radius_users:
        disconnect_user(sessions_dict[super_user][0], user)
        verify_sessions_disconnected(engines, user)

    # Create sessions for RADIUS users
    for user, password in zip(radius_users, radius_passwords):
        create_sessions(engines, user, password, 3)

    # Wait for all threads to complete
    wait_for_sessions_threads()

    # Verify the sessions are active
    for user in radius_users:
        verify_sessions_active(engines, user, expected_num_sessions=3)

    unset_radius_order(engines)

    # Reset channels and logs
    resest_channels()
    rotate_logs(engines)

    disconnect_user(sessions_dict[super_user][0], retry_run=False)

    verify_sessions_state(engines, users_sessions_should_be_active=[], users_sessions_should_be_closed=sessions_dict[radius_users[0]] + sessions_dict[radius_users[1]] + sessions_dict[super_user])

    sessions_dict.clear()

    # test radius disconnect users - Radius user can't disconnect now
    basic_user1, basic_password1 = create_user(system, 'basic1')
    basic_user2, basic_password2 = create_user(system, 'basic2')
    system_admin_user, system_admin_password = add_user_with_system_admin(engines, 'system_admin', apply=True)
    create_session_thread(engines, system_admin_user, system_admin_password)
    create_sessions(engines, super_user, super_pass, 3)
    create_sessions(engines, basic_user1, basic_password1, 3)
    create_session_thread(engines, basic_user2, basic_password2)
    wait_for_sessions_threads()
    set_radius_order(engines)

    for user, password in zip(radius_users, radius_passwords):
        create_sessions(engines, user, password, 3)
    wait_for_sessions_threads()

    # radius user disconnect other users without sudo permissions
    for user in [basic_user1, basic_user2, system_admin_user, radius_users[0]]:
        disconnect_result = disconnect_user(sessions_dict[radius_users[1]][0], user)
        assert "Failure" in disconnect_result, f"Expected 'Failure' in disconnect result, got {disconnect_result}"
        assert INSUFFICIENT_PRIVILEGES_ERROR_MSG in disconnect_result, f"Expected '{INSUFFICIENT_PRIVILEGES_ERROR_MSG}' error"

    disconnect_user(sessions_dict[radius_users[1]][0], radius_users[1], retry_run=False)

    verify_sessions_state(engines, users_sessions_should_be_active=sessions_dict[radius_users[0]] + sessions_dict[radius_users[1]] + sessions_dict[super_user] + sessions_dict[system_admin_user] + sessions_dict[basic_user1] + sessions_dict[basic_user2], users_sessions_should_be_closed=[])

    # radius user disconnect other users with sudo permissions
    for user in [basic_user1, basic_user2, system_admin_user, radius_users[1]]:
        disconnect_user(sessions_dict[radius_users[0]][0], user)
        verify_sessions_disconnected(engines, user)

    unset_radius_order(engines)

    # radius user disconnect thyself
    with allure.step('Radius user disconnect thyself'):
        disconnect_user(sessions_dict[radius_users[0]][0], radius_users[0], retry_run=False)

    verify_sessions_disconnected(engines, radius_users[0])

    sessions_dict.clear()

    create_session_thread(engines, super_user, super_pass)
    create_sessions(engines, system_admin_user, system_admin_password, 3)
    create_session_thread(engines, basic_user1, basic_password1)
    create_sessions(engines, basic_user2, basic_password2, 3)
    wait_for_sessions_threads()

    set_radius_order(engines)
    create_sessions(engines, radius_users[0], radius_passwords[0], 3)
    create_session_thread(engines, radius_users[1], radius_passwords[1])
    wait_for_sessions_threads()

    for user, count in zip(radius_users + [basic_user1, basic_user2, super_user, system_admin_user], [1, 3, 1, 3, 1, 3]):
        verify_sessions_active(engines, user, expected_num_sessions=count)

    unset_radius_order(engines)
    # Reset channels and logs
    resest_channels()
    rotate_logs(engines)

    with allure.step('Radius user disconnect all users'):
        disconnect_user(sessions_dict[radius_users[0]][0], retry_run=False)

    verify_sessions_state(engines, users_sessions_should_be_active=[], users_sessions_should_be_closed=sessions_dict[radius_users[0]] + sessions_dict[radius_users[1]] + sessions_dict[super_user] + sessions_dict[system_admin_user] + sessions_dict[basic_user1] + sessions_dict[basic_user2])


def config_radius_server(engines):
    """
    Configure the radius server for the test.
    """
    system = System(force_api=ApiType.NVUE)
    radius_config = RadiusPhysicalServer.SERVER_IPV4

    with allure.step('Configure the radius server'):
        radius_server = system.aaa.radius.server.server_id[radius_config.hostname]
        radius_server.set(AaaConsts.PORT, radius_config.port)
        radius_server.set(AaaConsts.SECRET, radius_config.secret)
        radius_server.set(AaaConsts.PRIORITY, radius_config.priority, apply=True, ask_for_confirmation='-y')


def set_radius_order(engines):
    """
    Set the radius order.
    """
    system = System(force_api=ApiType.NVUE)
    with allure.step('Set the radius order'):
        system.aaa.set('authentication-order', '10 radius')
        system.aaa.set('authentication-order', '20 local', apply=True, ask_for_confirmation='-y')


def unset_radius_order(engines):
    """
    Unset the radius order.
    """
    system = System(force_api=ApiType.NVUE)
    with allure.step('Unset the radius order'):
        system.aaa.unset('authentication-order', '10 radius')
        system.aaa.unset('authentication-order', '20 local', apply=True, ask_for_confirmation='-y')
