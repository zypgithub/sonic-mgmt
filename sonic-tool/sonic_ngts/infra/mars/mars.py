import requests
import os
import sys
import xml.etree.ElementTree as ET
from retry.api import retry_call

path = os.path.abspath(__file__)
sonic_ngts_path = path.split('/infra/')[0]
sys.path.append(sonic_ngts_path+"/infra/")

from logger.logger import logger


def get_mars_session_resource(mars_session_id):
    """
    Get session resource from MARS api
    :param mars_session_id: mars session id, e.g. 123456
    :return: xml tree object of the session id mars information
    """
    url = 'https://mars.nvidia.com/api/session/{SESSION_ID}.xml'.format(SESSION_ID=mars_session_id)
    return call_mars_rest_api_with_retry(url)


def call_mars_rest_api_with_retry(url):
    """
    Call call_mars_rest_api with retries
    :param url: base api command
    :return: query data
    """
    return retry_call(call_mars_rest_api, fargs=[url],  tries=10, delay=5, logger=logger)


def call_mars_rest_api(url):
    """
    Build mars query and return request data
    :param url: base api command
    :return: query data
    """
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    return root
