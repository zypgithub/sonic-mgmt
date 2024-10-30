"""For checking issue state based on supplied issue URL.
"""
import logging
import multiprocessing
import os
import re
import six
import requests
import pytest
import glob
import json
import datetime as dt

from abc import ABCMeta, abstractmethod
from perscache import Cache
from infra.tools.redmine.redmine_api import get_issues_active_status

logger = logging.getLogger(__name__)
cache = Cache()
dir_path = os.path.dirname(os.path.realpath(__file__))
DEFAULT_CONDITIONS_FILE = os.path.join(dir_path, "tests_mark_conditions*.yaml")

logger = logging.getLogger(__name__)


@cache(ttl=dt.timedelta(hours=36))
def get_conditions_list():
    logger.info('Reading conditions data from files')
    conditions_list = list()
    default_conditions_files = glob.glob(DEFAULT_CONDITIONS_FILE)
    conditions_files = [f for f in default_conditions_files if os.path.exists(f)]
    if not conditions_files:
        pytest.fail('There is no conditions files')

    try:
        logger.debug('Trying to load test mark conditions files: {}'.format(conditions_files))
        for conditions_file in conditions_files:
            with open(conditions_file) as f:
                logger.debug('Loaded test mark conditions file: {}'.format(conditions_file))
                conditions = yaml.safe_load(f)
                for key, value in list(conditions.items()):
                    conditions_list.append({key: value})
    except Exception as e:
        logger.error('Failed to load {}, exception: {}'.format(conditions_files, repr(e)), exc_info=True)
        pytest.fail('Loading conditions file "{}" failed. Possibly invalid yaml file.'.format(conditions_files))

    return conditions_list


@cache(ttl=dt.timedelta(hours=36))
def get_conditions_redmine_issues_status():
    logger.info('Reading Redmine Issues Status from API')
    conditions = get_conditions_list()
    ignore_list_string = json.dumps(conditions)
    all_redmine_issues = re.findall(r"https:\/\/redmine\.mellanox\.com\/issues\/(\d+)", ignore_list_string)
    issues_active_status_dict = get_issues_active_status(all_redmine_issues)
    return issues_active_status_dict


class IssueCheckerBase(six.with_metaclass(ABCMeta, object)):
    """Base class for issue checker
    """

    def __init__(self, url):
        self.url = url

    @abstractmethod
    def is_active(self):
        """
        Check if the issue is still active
        """
        return True


class RedmineIssueChecker(IssueCheckerBase):
    """
    Redmine issue state checker
    """
    NAME = 'Redmine'
    def __init__(self, url):
        super(RedmineIssueChecker, self).__init__(url)
    def is_active(self):
        """Check if the issue is still active.
        If unable to get issue state, always consider it as active.
        Returns:
            bool: False if the issue is closed else True.
        """
        redmine_issues_status = get_conditions_redmine_issues_status()
        issue_id = self.url.split('/issues/')[1]
        is_issue_active = redmine_issues_status[str(issue_id)]
        return is_issue_active


class GitHubIssueChecker(IssueCheckerBase):
    """GitHub issue state checker
    """

    NAME = 'GitHub'

    def __init__(self, url, proxies):
        super(GitHubIssueChecker, self).__init__(url)
        self.api_url = url.replace('github.com', 'api.github.com/repos')
        self.proxies = proxies

    def is_active(self):
        """Check if the issue is still active.

        If unable to get issue state, always consider it as active.

        Returns:
            bool: False if the issue is closed else True.
        """
        try:
            response = requests.get(self.api_url, proxies=self.proxies, timeout=10)
            response.raise_for_status()
            issue_data = response.json()
            if issue_data.get('state', '') == 'closed':
                logger.debug('Issue {} is closed'.format(self.url))
                labels = issue_data.get('labels', [])
                if any(['name' in label and 'duplicate' in label['name'].lower() for label in labels]):
                    logger.warning('GitHub issue: {} looks like duplicate and was closed. Please re-check and ignore'
                                   'the test on the parent issue'.format(self.url))
                return False
        except Exception as e:
            logger.error('Get details for {} failed with: {}'.format(self.url, repr(e)))

        logger.debug('Issue {} is active. Or getting issue state failed, consider it as active anyway'.format(self.url))
        return True


def issue_checker_factory(url, proxies):
    """Factory function for creating issue checker object based on the domain name in the issue URL.

    Args:
        url (str): Issue URL.

    Returns:
        obj: An instance of issue checker.
    """
    m = re.match('https?://([^/]+)', url)
    if m and len(m.groups()) > 0:
        domain_name = m.groups()[0].lower()
        if 'github' in domain_name:
            return GitHubIssueChecker(url, proxies)
        elif 'redmine' in domain_name:
            return RedmineIssueChecker(url)
        else:
            logger.error('Unknown issue website: {}'.format(domain_name))
    logger.error('Creating issue checker failed. Bad issue url {}'.format(url))
    return None


def check_issues(issues, proxies=None):
    """Check state of the specified issues.

    Because issue state checking may involve sending HTTP request. This function uses parallel run to speed up
    issue status checking.

    Args:
        issues (list of str): List of issue URLs.

    Returns:
        dict: Issue state check result. Key is issue URL, value is either True or False based on issue state.
    """
    checkers = [c for c in [issue_checker_factory(issue, proxies) for issue in issues] if c is not None]
    if not checkers:
        logger.error('No checker created for issues: {}'.format(issues))
        return {}

    check_results = multiprocessing.Manager().dict()
    check_procs = []

    def _check_issue(checker, results):
        results[checker.url] = checker.is_active()

    for checker in checkers:
        check_procs.append(multiprocessing.Process(target=_check_issue, args=(checker, check_results,)))

    for proc in check_procs:
        proc.start()
    for proc in check_procs:
        proc.join(timeout=60)

    return dict(check_results)
