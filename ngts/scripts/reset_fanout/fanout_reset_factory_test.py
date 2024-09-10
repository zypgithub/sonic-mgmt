#!/usr/bin/env python

import logging
import allure

FINISHED_LOG = 'Finished {}'

logger = logging.getLogger()


def test_fanout_reset_factory(topology_obj, onyx_image_url):
    """
    This function will perform installing new image on fanout switch and reset factory
    :param topology_obj: topology object fixture
    :param onyx_image_url: onyx image url
    """
    dut_engine = topology_obj.players['fanout']['engine']
    if onyx_image_url:
        install_new_image_on_fanout(dut_engine, onyx_image_url)
    reset_factory_fanout(dut_engine)


def reset_factory_fanout(dut_engine):
    reset_factory_log = "Performing reset factory on the fanout switch"
    with allure.step(reset_factory_log):
        logger.info(reset_factory_log)
        dut_engine.reload(reload_cmd_set=['reset factory keep-basic', 'YES'])
        show_version_concise_fanout(dut_engine)
        logger.info(FINISHED_LOG.format(reset_factory_log))


def fetch_image_on_fanout(dut_engine, onyx_img_url):
    fetch_image_log = "Fetching image on the fanout"
    with allure.step(fetch_image_log):
        logger.info(fetch_image_log)
        dut_engine.run_cmd('image fetch vrf mgmt {}'.format(onyx_img_url))
        logger.info(FINISHED_LOG.format(fetch_image_log))


def install_image_on_fanout(dut_engine, onyx_img_url):
    install_image_log = "Installing image on the fanout"
    with allure.step(install_image_log):
        onyx_img_name = _prepare_image_name(onyx_img_url)
        dut_engine.run_cmd('image install {}'.format(onyx_img_name))
        logger.info(FINISHED_LOG.format(install_image_log))


def _prepare_image_name(onyx_img_url):
    """
    From onyx image url returns image name
    :param onyx_img_url: url, Example: http://nbu-mtr-nfs.nvidia.com/mswg/release/sx_mlnx_os/lastrc_3_9_3000/X86_64/image-X86_64-3.9.3004-002.img
    :return: image-X86_64-3.9.3004-002.img
    """
    image_name_index = -1
    return onyx_img_url.split('/')[image_name_index]


def image_boot_next_fanout(dut_engine):
    image_boot_next_log = "Configuring image boot next on the fanout"
    with allure.step(image_boot_next_log):
        logger.info(image_boot_next_log)
        dut_engine.run_cmd('image boot next')
        logger.info(FINISHED_LOG.format(image_boot_next_log))


def show_version_concise_fanout(dut_engine):
    show_version_concise_log = "Show version concise on the fanout"
    with allure.step(show_version_concise_log):
        logger.info(show_version_concise_log)
        dut_engine.run_cmd('show version concise')
        logger.info(FINISHED_LOG.format(show_version_concise_log))


def install_new_image_on_fanout(dut_engine, onyx_img_url):
    install_new_image_on_fanout_log = "Installing new image on the fanout"
    with allure.step(install_new_image_on_fanout_log):
        logger.info(install_new_image_on_fanout_log)
        show_version_concise_fanout(dut_engine)
        fetch_image_on_fanout(dut_engine, onyx_img_url)
        install_image_on_fanout(dut_engine, onyx_img_url)
        image_boot_next_fanout(dut_engine)
        logger.info(FINISHED_LOG.format(install_new_image_on_fanout_log))
