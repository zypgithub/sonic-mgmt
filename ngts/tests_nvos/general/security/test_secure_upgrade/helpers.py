import logging
import random

from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.tests_nvos.general.security.test_secure_upgrade.constants import BEGIN_CMS, TEXT_TO_INJECT
from ngts.tools.test_utils import allure_utils as allure


def inject_string_to_image_k_lines_from_bottom(file, k, dst_file=None, text_to_inject: str = TEXT_TO_INJECT):
    cmd_runner = CmdRunner()
    dst_file = dst_file or file
    with allure.step(f'inject string {k} lines from the bottom: {dst_file}'):
        cmd = f'sed "$(($(wc -l < {file}) - {k - 1}))i {text_to_inject}" {file} > {dst_file}'
        cmd_runner.run_cmd(cmd)


def mess_image_signature(orig_img_path, dst_path) -> int:
    cmd_runner = CmdRunner()
    cmd = "tac " + orig_img_path + " | awk '/" + BEGIN_CMS + "/ {print NR}'"
    out, _, _ = cmd_runner.run_cmd_in_process(cmd)
    num_lines_from_bottom_of_signature_start = int(str(out).strip())
    logging.info(f'**** num_lines_from_bottom_of_signature_start - {num_lines_from_bottom_of_signature_start}')
    k = random.randint(1, num_lines_from_bottom_of_signature_start - 1)
    inject_string_to_image_k_lines_from_bottom(orig_img_path, k, dst_path)
    cmd_runner.run_cmd(f'chmod 777 {dst_path}')
    return num_lines_from_bottom_of_signature_start
