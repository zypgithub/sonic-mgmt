class DpuHost:
    def __init__(self, duthost, **kwargs):
        self.duthost = duthost
        self.mgmt_ip = kwargs['mgmt_ip']
        self.data_port = kwargs['data_port']
        self.name = kwargs['name']
        self.npu_data_port_ip = kwargs['npu_data_port_ip']
        self.dpu_data_port_ip = kwargs['dpu_data_port_ip']
        self.dataplane_mask_length = kwargs['dataplane_mask_length']


    def shell(self, cmd, module_ignore_errors=False, module_async=False):
        command = f'sudo proxy_ssh.py --dpu-mgmt-ip {self.mgmt_ip} --cmd "{cmd}"'
        if not module_ignore_errors:
            command += ' --validate'
        if module_async:
            command += ' --async'
        return self.duthost.shell(command)
