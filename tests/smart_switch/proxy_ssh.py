#!/usr/bin/python

import time
import argparse
import paramiko
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
sonic_username = os.popen('cat SONIC_USER').readline().strip()
sonic_password = os.popen('cat SONIC_PASSWORD').readline().strip()


def get_args():
    parser = argparse.ArgumentParser(description='Ssh proxy to run command on a DPU')
    parser.add_argument('--dpu-mgmt-ip', dest='dpu_mgmt_ip', required=True, help='The DPU mgmt IP')
    parser.add_argument('--cmd', dest='cmd', required=True, help='The command to send')
    parser.add_argument('--validate', dest='validate', action='store_true',
                        default=False, help='Whether validate the rc')
    parser.add_argument('--async', dest='async_mode', action='store_true',
                        default=False, help='Whether run the command in async mode')
    return parser.parse_args()


def ssh_command(host_ip, cmd, validate=False, async_mode=False):
    ssh.connect(hostname=host_ip, port=22, username=sonic_username, password=sonic_password)
    if not async_mode:
        _, stdout, stderr = ssh.exec_command(cmd)
        output = stdout.read().decode().strip()
        error = stderr.read().decode()
        rc = stdout.channel.recv_exit_status()
        if validate and rc != 0:
            ssh.close()
            raise Exception(error)
        if error:
            print(error)
        print(output)
    else:
        channel = ssh.invoke_shell()
        channel.send("nohup " + cmd + "\n")
        time.sleep(2)
    ssh.close()


def main():
    args = get_args()
    dpu_mgmt_ip = args.dpu_mgmt_ip
    cmd = args.cmd
    validate = args.validate
    async_mode = args.async_mode
    ssh_command(dpu_mgmt_ip, cmd, validate=validate, async_mode=async_mode)


if __name__ == "__main__":
    main()
