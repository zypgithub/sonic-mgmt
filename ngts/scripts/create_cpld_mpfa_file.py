#!/auto/app/Python-3.6.2/bin/python

import argparse
import logging
import sys
import traceback
import re
import os
import pathlib
from jinja2 import Environment, FileSystemLoader

repo_root = pathlib.Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
from ngts.constants.constants import LinuxConsts

logger = logging.getLogger("")


def set_logger(log_level):
    logging.basicConfig(level=log_level,
                        format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                        datefmt='%m-%d %H:%M')


def init_parser():
    description = ('Functionality of the script: \n'
                   'Creating an MPFA file for CPLD fwutil update on sonic.\n'
                   'The MPFA file is a zip file containing:\n'
                   '1) VME burn file\n'
                   '2) optional VME refresh file\n'
                   '3) metadata.ini file\n'
                   'for additional information:\n'
                   'https://wikinox.mellanox.com/pages/viewpage.action?spaceKey=SW'
                   '&title=SONiC+Platform+components+tools\n')

    parser = argparse.ArgumentParser(description=description)

    parser.add_argument('--FUI', required=True,
                        help='Name of the CPLD version i.e. FUI000076')

    parser.add_argument('--cpld_burn', required=True,
                        help='name of the burn VME file i.e.,\n'
                             'FUI000076_Burn_Panther_CR_CPLD000130_Rev0300_CPLD000128_Rev0600_CPLD000085_Rev1700.vme\n'
                             'should be located at path provided in argument mpfa_path')

    parser.add_argument('--cpld_refresh', required=False, default=None,
                        help='name of the refresh VME file i.e.,\n'
                             'FUI000076_Refresh_Panther_CR_CPLD000130_Rev0300_CPLD000128_Rev0600_CPLD000085_Rev1700.vme,\n'
                             'should be located at path provided in argument mpfa_path.\n'
                             'This argument is optional for platforms that do not require refresh (i.e.  spc6).')

    parser.add_argument('--mpfa_path', required=True,
                        help='path to where .mpfa file should be stored at the end of script run,\n'
                             'VME files also are expected to be located at this path.')

    parser.add_argument('--cplds', nargs='*', default=list(),
                        help='Should be specified only in cases where image name does not '
                        'indicate true cpld revision order.\n'
                        'see wiki: https://wikinox.mellanox.com/display/SW/How+to+update+a+tarball+for+fwutil+tests'
                        ' for more info.')

    parser.add_argument('-l', '--log_level', dest='log_level', default=logging.INFO, help='log verbosity')

    args, unknown = parser.parse_known_args()

    if unknown:
        raise Exception("unknown argument(s): {}".format(unknown))
    return args


def get_template():
    """
    :return: template object of file metadate_ini_template.txt
    """
    template_path = str(pathlib.Path(__file__).parent.absolute())
    template_name = "metadate_ini_template.txt"
    file_loader = FileSystemLoader(str(template_path))
    env = Environment(loader=file_loader)
    env.trim_blocks = True
    env.lstrip_blocks = True
    env.rstrip_blocks = True
    template = env.get_template(template_name)
    return template


def parse_cplds_revision(cpld_burn, cplds_arg_list):
    """
    :param cpld_burn: i.e FUI000076_Burn_Panther_CR_CPLD000130_Rev0300_CPLD000128_Rev0600_CPLD000085_Rev1700
    :param cplds_arg_list:  i.e [] or [CPLD000130_Rev0300, CPLD000128_Rev0600, CPLD000085_Rev1700]
    :return: list of tuples of CPLD revision and their indices
     i.e, [(1, CPLD000130_REV0300),(2, CPLD000128_REV0600),(3, CPLD000085_REV1700)]
    """
    cplds = cplds_arg_list if cplds_arg_list else \
        re.findall(r"CPLD\d+_[R|V][E|e][V|v|R|r]_*\d+", cpld_burn, re.IGNORECASE)
    cplds_correct_format = []
    for cpld in cplds:
        cpld_ver_rev_regex = re.search(r"CPLD(\d+)_[R|V][E|e][V|v|R|r]_*(\d+)", cpld, re.IGNORECASE)
        cpld_ver = cpld_ver_rev_regex.group(1)
        cpld_revision = cpld_ver_rev_regex.group(2)
        cpld = f"CPLD{cpld_ver}_REV{cpld_revision}"
        cplds_correct_format.append(cpld)
    return list(enumerate(cplds_correct_format, start=1))


def create_mpfa_file(FUI, cpld_burn, cpld_refresh, mpfa_path, cplds_arg_list):
    """
    :param FUI: i.e FUI000076
    :param cpld_burn: i.e FUI000076_Burn_Panther_CR_CPLD000130_Rev0300_CPLD000128_Rev0600_CPLD000085_Rev1700
    :param cpld_refresh: optional, i.e.
    FUI000076_Refresh_Panther_CR_CPLD000130_Rev0300_CPLD000128_Rev0600_CPLD000085_Rev1700
    :param mpfa_path: i.e, /auto/sw_system_release/hw_cpld/FUI000076
    :param cplds_arg_list: i.e [] or [CPLD000130_Rev0300, CPLD000128_Rev0600, CPLD000085_Rev1700]
    :return: none, creates FUI000076.mpfa at path mpfa_path
    """
    cplds = parse_cplds_revision(cpld_burn, cplds_arg_list)
    template = get_template()
    output = template.render(cpld_burn=cpld_burn, cpld_refresh=cpld_refresh or "", cplds=cplds)
    path = os.path.join(mpfa_path, FUI)
    os.mkdir(path)
    with open(os.path.join(path, "metadata.ini"), "w+") as f:
        f.write(output)
    logger.info(f"metadata.ini content:\n{output}")
    os.system(f"cp {mpfa_path}/{cpld_burn} {path}")
    if cpld_refresh:
        os.system(f"cp {mpfa_path}/{cpld_refresh} {path}")
    logger.info(f"Creating {FUI}.tar.gz file at {mpfa_path} for backup (this file can be seen in mc tool)")
    os.system(f"tar -czvf {mpfa_path}/{FUI}.tar.gz -C {path} .")
    logger.info(f"Creating {FUI}.mpfa file at {mpfa_path}")
    os.system(f"tar -czvf {mpfa_path}/{FUI}.mpfa -C {path} .")
    logger.info(f"file {mpfa_path}/{FUI}.mpfa was created successfully!")
    os.system(f"rm -rf {path}")


if __name__ == '__main__':
    try:
        args = init_parser()
        set_logger(args.log_level)
        create_mpfa_file(args.FUI, args.cpld_burn, args.cpld_refresh, args.mpfa_path, args.cplds)
        logger.info('Script Finished!')

    except Exception as e:
        traceback.print_exc()
        sys.exit(LinuxConsts.error_exit_code)
