import requests
import argparse
import datetime
import logging
import os
BASE_URL = "https://api.github.com"
BASE_PR_SEARCH_URL = "https://api.github.com/search/issues?q=type:pr + repo:Azure/sonic-mgmt"
TEAM_MEMBERS = ['nhe-NV', 'ppikh', "JibinBao", "roysr-nv", "AntonHryshchuk", "ihorchekh", "slutati1536"]

logger = logging.getLogger()


class GitHubApi:
    """
    This class allows user to search github prs
    Usage example:
    github = GitHubApi('user', 'api_token')
    github.get_pr_open_from_nvidia_verification_team()
    github.get_pr_merged_after_last_merge()
    """

    def __init__(self, github_username, api_token):
        self.auth = (github_username, api_token)

    def make_github_request(self, url):
        """
        Send API request to github
        :param url: github api url
        :return: dictionary with data
        """
        response = requests.get(url, auth=self.auth)
        response.raise_for_status()
        return response.json()

    def get_pr_open_from_nvidia_verification_team(self):
        for author in TEAM_MEMBERS:
            print(f"PR under author is {author}")
            pr_search_url_open_by_user = self.get_github_open_pr_url(author)
            self.get_pr_and_related_files(pr_search_url_open_by_user)

    def get_pr_merged_after_last_merge(self, last_merge_date):
        pr_search_url_merged_after_date = self.get_github_merged_pr_url(last_merge_date)
        self.get_pr_and_related_files(pr_search_url_merged_after_date)

    @staticmethod
    def get_github_open_pr_url(author):
        """
        Return the URL used to get the prs opened by user
        :param author: the author of the prs
        :return: URL used to get the prs opened by user
        """
        return f"{BASE_PR_SEARCH_URL} + is:open + author:{author}"

    @staticmethod
    def get_github_merged_pr_url(last_merge_date):
        """
        Return the URL used to get the prs merged since last merge date
        :param last_merge_date: last merge date
        :return: URL used to get the prs merged since last merge date
        """
        return f"{BASE_PR_SEARCH_URL} + merged:>={last_merge_date}"

    def get_pr_and_related_files(self, pr_search_url):
        """
        Get PRs and the files modified in the every pr
        :param pr_search_url: the url used to search the prs
        :return: None
        """
        pr_search_res = self.make_github_request(pr_search_url)
        pr_url_iter = ((pr['pull_request']['url'], pr['pull_request']['html_url']) for pr in pr_search_res['items'])
        for pr_url, pr_html_url in pr_url_iter:
            print(f"    {pr_html_url}")
            pr_file_resp = self.make_github_request(pr_url + '/files')
            for file in pr_file_resp:
                if file['status'] == 'modified':
                    print(f"        {file['filename']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.description = "Please input the parameter of last merge date"
    parser.add_argument("-l", "--last_merge_date", help="last merge date in format YYYY-MM-DD")
    args = parser.parse_args()
    default_last_merge_date = (datetime.datetime.now() + datetime.timedelta(days=-7)).strftime("%Y-%m-%d")
    last_merge_date = args.last_merge_date if args.last_merge_date else default_last_merge_date
    github_api = GitHubApi(os.getenv("GITHUB_USER"), os.getenv("GITHUB_API_TOKEN"))
    print("\n-----------------------------PR opened by our team ---------------------------------------")
    github_api.get_pr_open_from_nvidia_verification_team()
    print(f"\n----------------------------PR closed since {last_merge_date} ---------------------------")
    github_api.get_pr_merged_after_last_merge(last_merge_date)
