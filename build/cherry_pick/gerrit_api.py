import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import os
import re

from logger import logger

load_dotenv()

_GERRIT_USER = os.getenv("GERRIT_USERNAME")
assert _GERRIT_USER is not None, "GERRIT_USERNAME environment variable should be set"
_GERRIT_API_KEY = os.getenv("GEERIT_API_KEY")
assert _GERRIT_API_KEY is not None, "GERRIT_API_KEY environment variable should be set"

_GERRIT_HTTP_HEADERS = {
    "Content-Type": "application/json",
    "charset": "UTF-8"
}


# format with gerrit CR number
_GERRIT_TOPIC_URL_TEMPLATE = "https://git-nbu-sw.nvidia.com/r/a/changes/switchx%2Fsonic%2Fsonic-mgmt~{0}/topic"
_GERRIT_REVIEW_URL_TEMPLATE = \
    "https://git-nbu-sw.nvidia.com/r/a/changes/switchx%2Fsonic%2Fsonic-mgmt~{0}/revisions/1/review"
_GERRIT_CR_LINK_PATTERN = r'https://git-nbu-sw.nvidia.com/r/c/switchx/sonic/sonic-mgmt/\+/\d+'

# format with gerrit CR number
# _GERRIT_TOPIC_URL_TEMPLATE = "http://306f7b624d3d:8081/a/changes/playground-test~{0}/topic"
# _GERRIT_REVIEW_URL_TEMPLATE = \
#     "http://306f7b624d3d:8081/a/changes/playground-test~{0}/revisions/1/review"
# _GERRIT_CR_LINK_PATTERN = r'http://306f7b624d3d/c/playground-test/\+/\d+'

def set_topic(cr_number: str, topic: str)->tuple[int, str]:
    """
    cr_number: e.g. CR number is 290840 in the below link
        https://git-nbu-sw.nvidia.com/r/c/switchx/sonic/sonic-mgmt/+/290840
    topic: set up topic for the CR, the topic string can be separated with comma
        e.g. 'IGNORE', 'SKIP_BEAUTIFIER,SKIP_SPELLCHECK' are both valid topic(s)
    returns https status code and response body
    """
    put_body = {"topic": topic}
    gerrit_topic_url = _GERRIT_TOPIC_URL_TEMPLATE.format(cr_number)
    response = requests.put(gerrit_topic_url, auth=HTTPBasicAuth(_GERRIT_USER, _GERRIT_API_KEY),
                            json=put_body, headers=_GERRIT_HTTP_HEADERS)
    return (response.status_code, response.content.decode())

def review_plus_2(cr_num: str)->tuple[int, str]:
    """
    cr_num: the cr number, to add review +2
    returns http status code and response body
    """
    post_body = {
        "message": "Automatic +2 for cherry pick commits from community",
        "labels": {
            "Code-Review": 2
        }
    }
    res = requests.post(_GERRIT_REVIEW_URL_TEMPLATE.format(cr_num),
                        auth=HTTPBasicAuth(_GERRIT_USER, _GERRIT_API_KEY),
                        json=post_body, headers=_GERRIT_HTTP_HEADERS)
    return (res.status_code, res.content.decode())



def extract_cr_links(stdout: str)->list[str]:
    """"
    input is a string, normally stdout of command like `git review -Ry`
    return a list of CR links
    """
    links = re.findall(_GERRIT_CR_LINK_PATTERN, stdout)
    links.sort()
    return links

def add_topic_and_plus_2(cr_links: list[str]):
    cr_nums = [int(cr_link.split("/")[-1]) for cr_link in cr_links]
    cr_nums.sort()
    assert len(cr_nums) > 0, "No cr number found!"
    logger.info(f"cr_nums: {cr_nums}")
    logger.info(f"last cr_num: {cr_nums[-1]}")
    for i in range(len(cr_nums)-1):
        status_code, res_body = set_topic(cr_nums[i], "IGNORE")
        if status_code >= 400:
            raise Exception(f"unable to set topic for cr {cr_nums[i]}, {status_code}|{res_body}")
        logger.info(f"set topic IGNORE for {cr_nums[i]}, status code: {status_code}")
        status_code, res_body = review_plus_2(cr_nums[i])
        if status_code >= 400:
            raise Exception(f"unable to plus 2 for cr {cr_nums[i]}, {status_code}|{res_body}")
        logger.info(f"added plus 2 for {cr_nums[i]}, status code: {status_code}")
    status_code, res_body = set_topic(cr_nums[-1], "SKIP_BEAUTIFIER,SKIP_SPELLCHECK")
    if status_code >= 400:
        raise Exception(f"unable to set topic for cr {cr_nums[-1]}, {status_code}|{res_body}")
    logger.info(f"set topic SKIP_BEAUTIFIER,SKIP_SPELLCHECK for {cr_nums[-1]}, status code: {status_code}")
    status_code, res_body = review_plus_2(cr_nums[-1])
    if status_code >= 400:
        raise Exception(f"unable to plus 2 for cr {cr_nums[-1]}, {status_code}|{res_body}")
    logger.info(f"added plus 2 for {cr_nums[-1]}, status code: {status_code}")

if __name__ == '__main__':
    cr_nums = []
    with open("git-review-stdout.log") as f:
        stdout = f.read()
        cr_links = extract_cr_links(stdout)
        add_topic_and_plus_2(cr_links)
