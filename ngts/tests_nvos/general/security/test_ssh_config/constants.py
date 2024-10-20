

class SshConfigConsts:
    '''
    @summary: constants used in ssh config test
    '''
    MIN_AUTH_RETRIES = 3
    MAX_AUTH_RETRIES = 10
    MIN_LOGIN_TIMEOUT = 1
    MAX_LOGIN_TIMEOUT = 30
    MIN_LOGIN_PORT = 1
    MAX_LOGIN_PORT = 6400

    AUTH_RETRIES = 'authentication-retries'
    LOGIN_TIMEOUT = 'login-timeout'
    DEFAULT_PORT = 22
    PORTS = 'ports'
    PORT = 'port'

    SSH_CONFIG_CONNECTION_OPTIONS = ' -o ControlMaster=auto ' \
        '  -o ControlPersist=60s ' \
        '-o StrictHostKeyChecking=no ' \
        '-o UserKnownHostsFile=/dev/null ' \
        '-o ConnectTimeout=30 ' \
        '-o PubkeyAuthentication=no -o PreferredAuthentications=password -o NumberOfPasswordPrompts=100'
