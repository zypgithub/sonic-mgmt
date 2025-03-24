from smtp import send_email
from repo import GitCommit, CherryPickStatus
import os
import pytest

"""
Test module for email notification functionality in the cherry-pick utility.

This module contains test cases for the email notification system that reports
the results of cherry-pick operations. It tests both successful scenarios and
error conditions.
"""

@pytest.fixture(scope="function")
def setup_environment():
    os.environ["BUILD_URL"] = (
        "https://nbuprod.blsm.nvidia.com/nbu-sws-sonic/job/sonic_community_auto_merge/215"
    )

@pytest.mark.usefixtures("setup_environment")
def test_send_email_with_no_exception():
    """
    Test sending email with cherry pick result
    mocked git commit with cherry pick status 2
    """
    send_email(
        ["xixuej@nvidia.com"],
        "master",
        has_conflict=False,
        commits=[
            GitCommit(
                "1742142118",
                "1742140902",
                "Test commit[#1]",
                "1111111111111111111111111111111111111111",
                CherryPickStatus.ALREADY_INCLUDED  # already included
            ),
            GitCommit(
                "1742242118",
                "1742240902",
                "Test commit[#2]",
                "2222222222222222222222222222222222222222",
                CherryPickStatus.SUCCESS  # success
            )
        ],
        cr_on_top="https://git-nbu-sw.nvidia.com/r/c/switchx/sonic/sonic-mgmt/+/293664",
        triggered_by="Username",
        total_commits=2
    )

@pytest.mark.usefixtures("setup_environment")
def test_send_email_with_exception():
    """
    Test sending email with cherry pick exception
    """
    send_email(
        ["xixuej@nvidia.com"],
        "master",
        exception=Exception("test exception")
    )
