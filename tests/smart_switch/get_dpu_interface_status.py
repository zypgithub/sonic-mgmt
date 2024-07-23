import os
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

dpus = ["169.254.200.1", "169.254.200.2", "169.254.200.3", "169.254.200.4"]

for dpu in dpus:
    ssh.connect(hostname=dpu, port=22, username="admin", password="YourPaSsWoRd")
    stdin, stdout, stderr = ssh.exec_command('show interface status')
    output = stdout.read().decode()
    os.system(f'echo "{output}" > /tmp/interface_status_output_{dpu}')
    ssh.close()
