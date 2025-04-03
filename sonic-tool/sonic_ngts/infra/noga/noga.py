import requests
import requests_cache
import time
from infra.logger.logger import logger

CACHE_EXPIRATION_TIMEOUT = 43200
CACHE_FILE_PATH = '/tmp/noga_cache'


def get_noga_resource(**kwargs):
    """
    Get resource from noga, first validate the query arguments, then call noga
    :param kwargs: query arguments
    :return: query data
    """
    url = 'https://noga.nvidia.com/app/server/php/rest_api'
    return call_noga_rest_api_with_retry(url, **dict(api_cmd='get_resources', **kwargs))


def get_noga_resource_data(**kwargs):
    """
    Get resource details from noga, first validate the query arguments, then call noga
    :param kwargs: query arguments
    :return: query data
    """
    url = 'https://noga.nvidia.com/app/server/php/rest_api/'
    return call_noga_rest_api_with_retry(url, **dict(api_cmd='get_resource_data', **kwargs))


def call_noga_rest_api_with_retry(url, **kwargs):
    """
    Call call_noga_rest_api with retries
    :param url: base api command
    :param kwargs: api arguments
    :return: query data
    """
    try_num = 0
    tries = 3
    while try_num < tries:
        try:
            return call_noga_rest_api(url, **kwargs)
        except Exception as err:
            try_num += 1
            logger.warning("Unable to get Noga resource:{}, Try number: {}/{}".format(kwargs, try_num, tries+1))
            logger.debug(err)
            time.sleep(1)
    return call_noga_rest_api(url, **kwargs)


def call_noga_rest_api(url, use_cache=True, **kwargs):
    """
    Build noga query and return request data
    :param url: base api command
    :param use_cache: if want to use cache for Noga requests - True, else False
    :param kwargs: api arguments
    :return: query data
    """
    if use_cache:
        requests_cache.install_cache(CACHE_FILE_PATH, expire_after=CACHE_EXPIRATION_TIMEOUT)
    response = requests.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()["data"]
