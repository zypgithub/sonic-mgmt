import logging
import shutil
import re
import os
import argparse
import tarfile
import gzip
from pathlib import Path

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.topology_tools.nogaq import get_noga_resource_data

logger = logging.getLogger()


class DumpCleanerConfig:
    TMP_TECHSUPPORT_DUMP = "/tmp/"
    EXTRACTED_FILES_FOLDER = "tmp_extracted_files"
    OUTPUT_FILES_FOLDER = ""
    REMOVED_FILENAME = ['sai', 'sdk']
    FORCE_PREFIX = ['log']
    PLATFORM = None


def is_compressed_file(file_path):
    file_name, file_extension = os.path.splitext(file_path)
    compressed_format = ['.tar', '.gz']
    return file_extension in compressed_format


class LogFiles:
    def __init__(self, log_file, hostname=None, platform=None):
        self.log_file_list = []

        self.log_file_list.append(log_file)

        if hostname is None:
            pattern = r"sonic_dump_(.*?)_"
            match = re.search(pattern, log_file)

            if match:
                self.hostname = match.group(1)
            else:
                raise ValueError(
                    "Can not capture hostname from dump file. Need to set parameter `hostname` manually")
        else:
            self.hostname = hostname

        self.platform = platform

    def _get_platform(self):

        if self.platform is not None:
            return self.platform

        noga_query_data = get_noga_resource_data(resource_name=self.hostname)
        switch_type = noga_query_data['attributes']['Specific']['switch_type']

        if not switch_type:
            raise ValueError('Noga entry "Type" for device %s is empty',
                             noga_query_data['attributes']['Specific']['Name'])

        # Some Switch type still has internal name inside.
        switch_type = switch_type.split(" - ")[0]

        return switch_type

    def clean_dump(self):
        for file in self.log_file_list:
            is_compressed = is_compressed_file(file)
            filename = Path(file).name
            if is_compressed:
                path = extract_compressed_file(file)
                if path is None:
                    raise FileExistsError(f"Extract {file} failed!")
            elif os.path.isdir(file):
                shutil.copytree(file, DumpCleanerConfig.OUTPUT_FILES_FOLDER)
                path = os.path.join(DumpCleanerConfig.OUTPUT_FILES_FOLDER, filename)
            else:
                shutil.copy2(file, DumpCleanerConfig.OUTPUT_FILES_FOLDER)
                path = os.path.join(DumpCleanerConfig.OUTPUT_FILES_FOLDER, filename)

            self._replace_content_hostname(path)
            new_dir = self._rename_log_dir(path)

            if is_compressed:
                compress_uncompressed_file(new_dir)

    def _replace_content_hostname(self, dump_dir):
        logger.info(f"==============Start to handle files' content==============")

        def _get_new_content(contents):
            new_contents = contents.replace(self.hostname, platform)
            return new_contents

        platform = self._get_platform()

        dump_dir_path = Path(dump_dir)

        if dump_dir_path.is_file():
            walk = [(dump_dir_path.absolute().parent, [], [dump_dir_path.name])]
        else:
            walk = os.walk(dump_dir_path)

        for root, _, files in walk:
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    if file.endswith(".gz"):
                        # To ensure it safe, create a tmp instead of modified it.
                        temp_path = file_path[:-3]
                        try:
                            with gzip.open(file_path, 'rt') as f_in, gzip.open(temp_path, 'wt') as f_out:
                                for line in f_in:
                                    modified_line = _get_new_content(line)
                                    f_out.write(modified_line)
                        except Exception as e:
                            raise e
                        finally:
                            os.remove(file_path)
                            os.rename(temp_path, file_path)
                    else:
                        with open(file_path, 'r+', encoding='utf-8') as target_file:
                            content = target_file.read()
                            new_content = _get_new_content(content)
                            if content != new_content:
                                target_file.seek(0)
                                target_file.truncate()
                                target_file.write(new_content)
                    logger.info(f"Modified content in '{file_path}'")
                except PermissionError:
                    logger.info(f"File {file_path} is permission denied ")
                except UnicodeDecodeError:
                    logger.info(f"File {file_path} can not be decoded by utf-8")

    def _rename_log_dir(self, dump_dir):
        platform = self._get_platform()

        if self.hostname in dump_dir:
            new_dir = dump_dir.replace(self.hostname, platform)
        else:
            new_dir = dump_dir

        os.rename(Path(dump_dir), new_dir)

        return new_dir


def check_if_need_to_remove(filename):
    for p in DumpCleanerConfig.FORCE_PREFIX:
        sub_path = ''.join(filename.split("/")[1:])
        if not sub_path.startswith(p):
            return True
    for p in DumpCleanerConfig.REMOVED_FILENAME:
        if p in filename:
            return True
    return False


def delete_files(fname, folder=True):
    if folder:
        logger.info(f"Deleting the folder: {fname}")
        os.system(f"rm -rf {fname}")
        logger.info(f"Deleted the folder: {fname}")
    else:
        logger.info(f"Deleting the file: {fname}")
        os.system(f"rm -rf {fname}")
        logger.info(f"Deleted the file: {fname}")


def extract_compressed_file(compressed_file):
    if "tar.gz" in compressed_file:
        folder = os.path.join(DumpCleanerConfig.TMP_TECHSUPPORT_DUMP, DumpCleanerConfig.EXTRACTED_FILES_FOLDER)

        if os.path.exists(folder):
            delete_files(folder, folder=True)

        os.makedirs(folder, exist_ok=True, )

        logger.info(f"==============Extract dump file to {folder}==============")

        try:
            # os.system(f'tar -xf {compressed_file} -C {folder}')
            with tarfile.open(compressed_file, 'r:gz') as tar_ref:
                members = tar_ref.getmembers()
                for member in members:
                    member_name = member.path
                    if check_if_need_to_remove(member_name):
                        continue

                    try:
                        tar_ref.extract(member, path=folder)
                    except Exception as e:
                        logger.info(f"Error extracting {member.name}: {e}")

        except Exception as err:
            raise err

        filename = Path(compressed_file).name.strip('.tar.gz')

        logger.info(f"==============Extracting dump file finished==============")

        return os.path.join(folder, filename)

    return None


def compress_uncompressed_file(dir_path):
    logger.info("==============Start to compress cleaned dump file==============")
    output_filename = Path(dir_path).name + ".tar.gz"
    target_path = os.path.join(DumpCleanerConfig.OUTPUT_FILES_FOLDER, output_filename)
    with tarfile.open(target_path, "w:gz") as tar:
        tar.add(dir_path, arcname=os.path.basename(dir_path))
    delete_files(dir_path, folder=True)
    logger.info(f"==============Cleaned dump file save to {target_path}==============")


def get_dump_from_dut(hostname, username, password):
    sonic = LinuxSshEngine(ip=hostname, username=username, password=password, ssh_port=22)

    cmd = "show techsupport"

    logger.info(f"==============Start to run techsupport one DUT: {cmd}==============")
    out = sonic.run_cmd(cmd).split("\n")

    if out[0].startswith("Removing stale lock"):
        out = sonic.run_cmd(cmd).split("\n")

    while out:
        if out[-1]:
            break
        else:
            out.pop()

    dut_dump_path = out[-1]

    logger.info(f"==============Dump file collected: {dut_dump_path}==============")
    logger.info("==============Start to fetch the dump from the dut==============")

    try:
        sonic.copy_file(direction="get",
                        dest_file=DumpCleanerConfig.TMP_TECHSUPPORT_DUMP,
                        source_file=dut_dump_path,
                        file_system="")
        dut_dump = DumpCleanerConfig.TMP_TECHSUPPORT_DUMP + dut_dump_path.split("/")[-1]
        if Path(dut_dump).exists():
            logger.info(f'Finish fetch dump from dut, saved: {dut_dump}')
            return dut_dump
        else:
            raise Exception(f'dut dump: {dut_dump} does not exist')
    except Exception as err:
        logger.info(f'Failed to fetch dump file from DUT: {str(err)}')
        raise Exception(f'Failed run the command to collect dump file from dut')


def init_parser():
    description = ('Functionalities of the script: \n'
                   '1. Fetches techsupport dumps from remote or local filesystem \n'
                   '2. Automatically scans and replaces all occurrences of the device hostname '
                   'within the techsupport dump with platform.\n'
                   '3. Enables the removal of files or directories from the dump that contain user-specified keywords.')

    epilog = 'The script works by given `hostname` or `dump-path`'

    parser = argparse.ArgumentParser(description=description, epilog=epilog,
                                     formatter_class=argparse.RawTextHelpFormatter)

    # group = parser.add_mutually_exclusive_group(required=True)
    parser.add_argument("-f", "--file", default=None, dest="dump_file", help="Path of the dump or syslog file/dir")

    parser.add_argument("-H", "--hostname", default=None, dest="hostname", help="Hostname of DUT.")

    parser.add_argument("-t", "--temp-path", dest="temp_path", default=DumpCleanerConfig.TMP_TECHSUPPORT_DUMP,
                        help="Path of temporary files.")

    parser.add_argument("-o", "--output-path", dest="output_path", default="",
                        help="Path of output files.")

    parser.add_argument("-P", "--platform", dest="platform", default=None,
                        help="Manually set the platform name.")

    parser.add_argument("-c", "--clean-keywords", dest="clean_keywords", nargs='*', default=[],
                        help="A list of keywords, files/directories whose name include any keywords will be removed.")

    parser.add_argument("-u", "--username", dest="username", default=None,
                        help="Username of DUT.")

    parser.add_argument("-p", "--password", dest="password", default=None,
                        help="Password of DUT.")

    parser.add_argument('-l', '--log-level', dest='log_level', default=logging.INFO, help='log verbosity')

    arguments, unknown = parser.parse_known_args()
    if unknown:
        raise Exception("unknown argument(s): {}".format(unknown))
    return arguments


def main():
    arguments = init_parser()

    username = arguments.username if arguments.username is not None else os.getenv("DUT_USERNAME")
    password = arguments.password if arguments.password is not None else os.getenv("DUT_PASSWORD")

    filepath = arguments.dump_file

    logger.setLevel(arguments.log_level)
    handler = logging.StreamHandler()
    logger.addHandler(handler)

    if filepath is not None:
        remote = False
        logger.info(f"`file` is given. Use the local dump file.")
    else:
        if arguments.hostname is None:
            raise ValueError("`hostname` argument is required when `dump-file` is empty.")
        remote = True
        logger.info(f"Copy local dump file from DUT {arguments.hostname}.")
        filepath = get_dump_from_dut(arguments.hostname, username, password)

    log = LogFiles(log_file=filepath, hostname=arguments.hostname, platform=arguments.platform)

    DumpCleanerConfig.TMP_TECHSUPPORT_DUMP = arguments.temp_path
    if len(arguments.clean_keywords) > 0:
        DumpCleanerConfig.REMOVED_FILENAME = arguments.clean_keywords
    DumpCleanerConfig.OUTPUT_FILES_FOLDER = arguments.output_path

    log.clean_dump()

    if remote:
        # Delete dump file copy from DUT
        os.remove(filepath)


if __name__ == '__main__':
    main()
