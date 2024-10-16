from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine


class SecureBootTool:

    @classmethod
    def is_secure_boot_enabled(cls, player: LinuxSshEngine) -> bool:
        output: str = player.run_cmd('mokutil --sb-state')
        return output.replace('SecureBoot ', '').strip().lower() == 'enabled'

    @classmethod
    def is_secure_boot_disabled(cls, player: LinuxSshEngine) -> bool:
        return not cls.is_secure_boot_enabled(player)

    @classmethod
    def is_dev_system(cls, player: LinuxSshEngine) -> bool:
        out = (player.run_cmd('mokutil --db | grep DEV')).strip()
        return bool(out)

    @classmethod
    def is_prod_system(cls, player: LinuxSshEngine) -> bool:
        return not cls.is_dev_system(player)
