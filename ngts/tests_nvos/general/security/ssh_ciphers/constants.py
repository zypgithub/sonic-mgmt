class SshCiphersConsts:
    TIMEOUT = 4
    PROTOCOL = 'protocol'
    CIPHERS = 'ciphers'
    MACS = 'macs'
    KEX_ALGOS = 'kex-algorithms'
    HOST_KEY_ALGOS = 'host-key-algorithms'
    PUBKEY_ACCEPTED_ALGOS = 'pubkey-accepted-algorithms'
    COMPRESSION = 'compression'
    X11FORWARDING = 'x11forwarding'
    ALLOWTCPFORWARDING = 'allowtcpforwarding'
    STRICT = 'strict'
    STRICT_HOST_KEY_CHECKING = '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'

    FLAGS = {
        CIPHERS: '-c ',
        MACS: '-m ',
        KEX_ALGOS: '-o KexAlgorithms=',
        HOST_KEY_ALGOS: '-o HostKeyAlgorithms=',
        PUBKEY_ACCEPTED_ALGOS: '-o PubkeyAcceptedAlgorithms=',
    }
    ADDITIONAL_FLAGS = {
        PUBKEY_ACCEPTED_ALGOS: '-o IdentitiesOnly=yes -i '
    }
    DEFAULT_VALUES = {
        CIPHERS: ['aes256-ctr', 'aes192-ctr', 'aes128-ctr', 'aes128-gcm@openssh.com', 'aes256-gcm@openssh.com'],
        MACS: ['hmac-sha2-256', 'hmac-sha2-512', 'hmac-sha2-512-etm@openssh.com', 'hmac-sha2-256-etm@openssh.com'],
        KEX_ALGOS: ['curve25519-sha256', 'curve25519-sha256@libssh.org', 'diffie-hellman-group16-sha512', 'diffie-hellman-group18-sha512', 'diffie-hellman-group14-sha256'],
        HOST_KEY_ALGOS: ['rsa-sha2-512', 'rsa-sha2-256', 'ecdsa-sha2-nistp256'],
        PUBKEY_ACCEPTED_ALGOS: ['ecdsa-sha2-nistp256-cert-v01@openssh.com',
                                'ecdsa-sha2-nistp384-cert-v01@openssh.com',
                                'ecdsa-sha2-nistp521-cert-v01@openssh.com',
                                'ecdsa-sha2-nistp256',
                                'ecdsa-sha2-nistp384',
                                'ecdsa-sha2-nistp521',
                                'ssh-ed25519-cert-v01@openssh.com',
                                'rsa-sha2-512-cert-v01@openssh.com',
                                'rsa-sha2-256-cert-v01@openssh.com',
                                'ssh-ed25519',
                                'rsa-sha2-512',
                                'rsa-sha2-256',
                                ]
    }
    POSSIBLE_VALUES = {
        CIPHERS: ['aes256-ctr',
                  'aes192-ctr',
                  'aes128-ctr',
                  'aes128-gcm@openssh.com',
                  'aes256-gcm@openssh.com',
                  '3des-cbc',
                  'aes128-cbc',
                  'aes192-cbc',
                  'aes256-cbc',
                  'chacha20-poly1305@openssh.com'
                  ],
        MACS: ['hmac-sha1-96',
               'hmac-md5',
               'hmac-md5-96',
               'umac-64@openssh.com',
               'umac-128@openssh.com',
               'hmac-sha1-etm@openssh.com',
               'hmac-sha1-96-etm@openssh.com',
               'hmac-md5-etm@openssh.com',
               'hmac-md5-96-etm@openssh.com',
               'umac-64-etm@openssh.com',
               'umac-128-etm@openssh.com'
               ],
        KEX_ALGOS: ['curve25519-sha256',
                    'curve25519-sha256@libssh.org',
                    'diffie-hellman-group16-sha512',
                    'diffie-hellman-group18-sha512',
                    'diffie-hellman-group14-sha256',
                    'diffie-hellman-group16-sha512',
                    'diffie-hellman-group18-sha512',
                    'diffie-hellman-group14-sha256',
                    'sntrup761x25519-sha512@openssh.com',
                    'diffie-hellman-group-exchange-sha256',
                    'ecdh-sha2-nistp384',
                    'sntrup761x25519-sha512',
                    'ecdh-sha2-nistp256',
                    'ecdh-sha2-nistp521'
                    ],
        HOST_KEY_ALGOS: ['rsa-sha2-512',
                         'rsa-sha2-256',
                         'ecdsa-sha2-nistp256',
                         'ecdsa-sha2-nistp384',
                         'ecdsa-sha2-nistp521',
                         'ssh-ed25519',
                         'ecdsa-sha2-nistp256-cert-v01@openssh.com',
                         'ecdsa-sha2-nistp384-cert-v01@openssh.com',
                         'ecdsa-sha2-nistp521-cert-v01@openssh.com',
                         'ssh-ed25519-cert-v01@openssh.com',
                         'rsa-sha2-512-cert-v01@openssh.com',
                         'rsa-sha2-256-cert-v01@openssh.com',
                         'ssh-rsa-cert-v01@openssh.com',
                         'ssh-rsa'
                         ],
        PUBKEY_ACCEPTED_ALGOS: ['ecdsa-sha2-nistp256-cert-v01@openssh.com',
                                'ecdsa-sha2-nistp384-cert-v01@openssh.com',
                                'ecdsa-sha2-nistp521-cert-v01@openssh.com',
                                'ecdsa-sha2-nistp256',
                                'ecdsa-sha2-nistp384',
                                'ecdsa-sha2-nistp521',
                                'ssh-ed25519-cert-v01@openssh.com',
                                'rsa-sha2-512-cert-v01@openssh.com',
                                'rsa-sha2-256-cert-v01@openssh.com',
                                'ssh-ed25519',
                                'rsa-sha2-512',
                                'rsa-sha2-256',
                                'ssh-rsa',
                                'ssh-rsa-cert-v01@openssh.com'
                                ]
    }
    INVALID_VALUES = {
        CIPHERS: ['3des-cbc',
                  'aes128-cbc',
                  'aes192-cbc',
                  'aes256-cbc',
                  'chacha20-poly1305@openssh.com'
                  ],
        MACS: ['hmac-sha1-96',
               'hmac-md5',
               'hmac-md5-96',
               'umac-64@openssh.com',
               'umac-128@openssh.com',
               'hmac-sha1-etm@openssh.com',
               'hmac-sha1-96-etm@openssh.com',
               'hmac-md5-etm@openssh.com',
               'hmac-md5-96-etm@openssh.com',
               'umac-64-etm@openssh.com',
               'umac-128-etm@openssh.com'
               ],
        KEX_ALGOS: ['sntrup761x25519-sha512@openssh.com',
                    'sntrup761x25519-sha512',
                    'kex-strict-s-v00@openssh.com',
                    'ecdh-sha2-nistp256',
                    'ecdh-sha2-nistp384',
                    'ecdh-sha2-nistp521',
                    'diffie-hellman-group-exchange-sha256',
                    ],
        HOST_KEY_ALGOS: ['ecdsa-sha2-nistp256-cert-v01@openssh.com',
                         'ecdsa-sha2-nistp384-cert-v01@openssh.com',
                         'ecdsa-sha2-nistp521-cert-v01@openssh.com',
                         'ecdsa-sha2-nistp384',
                         'ecdsa-sha2-nistp521',
                         'ssh-ed25519-cert-v01@openssh.com',
                         'rsa-sha2-512-cert-v01@openssh.com',
                         'rsa-sha2-256-cert-v01@openssh.com',
                         'ssh-rsa-cert-v01@openssh.com',
                         'ssh-ed25519',
                         'ssh-rsa'
                         ],
        PUBKEY_ACCEPTED_ALGOS: ['ssh-rsa', 'ssh-rsa-cert-v01@openssh.com']
    }
    PATTERNS = {
        CIPHERS: r'kex: client->server cipher: ([^\s]+)',           # Group 1: cipher name
        MACS: r'kex: client->server cipher: (?:[^\s]+) MAC: ([^\s]+)',  # Group 1: MAC algorithm (non-capturing cipher)
        KEX_ALGOS: r'kex: algorithm: ([^\s]+)',                     # Group 1: KEX algorithm
        HOST_KEY_ALGOS: r'kex: host key algorithm: (?!\(no)([^\s]+)',  # Group 1: host key algorithm (exclude "(no match)")
    }

    # Public Key Authentication Patterns
    PUBKEY_ACCEPTED_ALGOS_PATTERN = r'Server accepts key: ([^\s]+) ([^\s]+)'
    PUBLIC_KEY_AUTHENTICATION_PATTERN = r'Authenticated to .+ using "publickey"'

    PUBLIC_KEY_OFFERING_PATTERN = r'Offering public key: .+ explicit'

    ERROR_PATTERN_PREFIX = 'Unable to negotiate with.*'
    ERROR_PATTERNS = {
        CIPHERS: rf'{ERROR_PATTERN_PREFIX} no matching cipher found.',
        MACS: rf'{ERROR_PATTERN_PREFIX} no matching MAC found.',
        KEX_ALGOS: rf'Unsupported KEX algorithm.*|Bad SSH2 KexAlgorithms.*',
        HOST_KEY_ALGOS: rf'{ERROR_PATTERN_PREFIX} no matching host key type found.',
        PUBKEY_ACCEPTED_ALGOS: rf'{ERROR_PATTERN_PREFIX} no matching pubkey accepted key type found.'
    }
