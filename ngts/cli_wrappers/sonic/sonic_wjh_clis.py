class SonicWjhCli:
    """
    This class hosts SONiC What Just Happened (WJH) CLI methods and related utilities
    """

    def __init__(self, engine):
        self.engine = engine

    def show_wjh_configuration_channels(self):
        return self.engine.run_cmd('show what-just-happened configuration channels')

    def show_wjh_configuration_buffer_profile(self, profile_name):
        return self.engine.run_cmd(f'show what-just-happened configuration buffer-profile {profile_name}')

    def show_wjh_statistics(self):
        return self.engine.run_cmd('show what-just-happened statistics')

    def show_wjh_drops(self, channel=None):
        cmd = 'show what-just-happened drops'
        if channel:
            cmd += f' {channel}'
        return self.engine.run_cmd(cmd)

    def config_wjh_channel_state(self, channel_name, state):
        return self.engine.run_cmd(f'sudo config what-just-happened channel state {channel_name} {state}')
