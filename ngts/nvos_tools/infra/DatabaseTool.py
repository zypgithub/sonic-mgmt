import logging
import socket

from ngts.nvos_tools.infra.EngineAdapterTool import EngineAdapterTool

logger = logging.getLogger()


class DatabaseTool:

    @staticmethod
    def _run_cmd(engine, cmd):
        """Run command on engine, handling both SSH and serial engines."""
        return EngineAdapterTool.run_cmd(engine, cmd)

    @staticmethod
    def redis_cli_hset(engine, db_num, db_config, param, value):
        cmd = f'redis-cli -n {db_num} hset "{db_config}" "{param}" "{value}"'
        logging.info(f'Running {cmd}')
        return engine.run_cmd(cmd)

    @staticmethod
    def redis_cli_hget(engine, db_num, db_config, param):
        cmd = f'redis-cli -n {db_num} hget "{db_config}" "{param}"'
        logging.info(f'Running {cmd}')
        return engine.run_cmd(cmd)

    @staticmethod
    def sonic_db_cli_hset(engine, asic, db_name, db_config, param, value):
        asic = f"-n {asic} " if asic else ""
        cmd = f'sonic-db-cli {asic}{db_name} hset "{db_config}" "{param}" "{value}"'
        logging.info(f'Running {cmd}')
        return engine.run_cmd(cmd)

    @staticmethod
    def sonic_db_cli_hget(engine, asic, db_name, db_config, param):
        asic = f"-n {asic} " if asic else ""
        cmd = f'sonic-db-cli {asic}{db_name} hget "{db_config}" "{param}"'
        logging.info(f'Running {cmd}')
        return engine.run_cmd(cmd)

    @staticmethod
    def sonic_db_cli_hdel(engine, asic, db_name, db_config, param):
        asic = f"-n {asic} " if asic else ""
        cmd = f'sonic-db-cli {asic}{db_name} hdel "{db_config}" "{param}"'
        logging.info(f'Running {cmd}')
        return engine.run_cmd(cmd)

    @staticmethod
    def sonic_db_cli_get_keys(engine, asic, db_name, grep_str=None):
        asic = f"-n {asic} " if asic else ""
        cmd = f"sonic-db-cli {asic}{db_name} keys \\*"
        if grep_str:
            cmd += f" | grep {grep_str}"
        logging.info(f'Running {cmd}')
        return engine.run_cmd(cmd)

    @staticmethod
    def sonic_db_run_get_keys_in_docker(docker_name, engine, asic, db_name, grep_str=None):
        asic = f"-n {asic} " if asic else ""
        cmd = f'docker exec -it {docker_name} sonic-db-cli {asic}{db_name} keys \\*'
        if grep_str:
            cmd += f" | grep {grep_str}"
        logging.info(f'Running {cmd}')
        return engine.run_cmd(cmd)

    @staticmethod
    def sonic_db_run_hget_in_docker(docker_name, engine, asic, db_name, db_config, param):
        asic = f"-n {asic} " if asic else ""
        cmd = f'docker exec -it {docker_name} sonic-db-cli {asic}{db_name} hget {db_config} {param}'
        logging.info(f'Running {cmd}')
        return engine.run_cmd(cmd)

    @staticmethod
    def sonic_db_cli_hgetall(engine, asic, db_name, table_name):
        try:
            cmd = DatabaseTool._get_hgetall_cmd(asic, db_name, table_name)
            return DatabaseTool._run_cmd(engine, cmd)
        except socket.error as e:
            logging.info('Got "OSError: Socket is closed" - Current engine was also disconnected')
            engine.disconnect()
            return "Action succeeded"

    @staticmethod
    def sonic_db_cli_hgetall_serial(engine, asic, db_name, table_name):
        engine.sendline(DatabaseTool._get_hgetall_cmd(asic, db_name, table_name))

    @staticmethod
    def _get_hgetall_cmd(asic, db_name, table_name):
        asic = f"-n {asic} " if asic else ""
        cmd = f'sonic-db-cli {asic}{db_name} HGETALL {table_name}'
        logging.info(f'Running {cmd}')
        return cmd
