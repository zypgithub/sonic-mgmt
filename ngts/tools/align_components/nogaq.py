#!/bin/env python

import json
import logging
import time

import requests

logger = logging.getLogger(__name__)

CACHE_EXPIRATION_TIMEOUT = 43200
CACHE_FILE_PATH = '/tmp/noga_cache'
CACHE_FILE_NAME = '/tmp/noga_cache.sqlite'
URL = 'https://noga.nvidia.com/app/server/php/rest_api/'


def get_noga_resource(**kwargs):
    """
    Get resource from noga, first validate the query arguments, then call noga
    :param kwargs: query arguments
    :return: query data
    """
    return call_noga_rest_api_with_retry(URL, **dict(api_cmd='get_resources', **kwargs))


def get_noga_resource_data(**kwargs):
    """
    Get resource details from noga, first validate the query arguments, then call noga
    :param kwargs: query arguments
    :return: query data
    """
    return call_noga_rest_api_with_retry(URL, **dict(api_cmd='get_resource_data', **kwargs))


def get_noga_entire_resource_data(**kwargs):
    """
    Get entire resource details from noga, first validate the query arguments, then call noga
    :param kwargs: query arguments
    :return: query data
    """
    return call_noga_rest_api_with_retry(URL, **dict(api_cmd='get_entire_resource_data', **kwargs))


def call_noga_rest_api(url, **kwargs):
    """
    Build noga query and return request data
    :param url: base api command
    :param kwargs: api arguments
    :return: query data
    """
    response = requests.get(url, params=kwargs)
    response.raise_for_status()
    try:
        results = response.json()['data']
    except BaseException:
        results = json.loads(response.text)
    return results


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
            logger.warning(" Unable to get Noga resource:%s, Try number: %s/%s", kwargs, try_num, tries + 1)
            logger.debug(err)
            time.sleep(try_num * 5)
    return call_noga_rest_api(url, **kwargs)
