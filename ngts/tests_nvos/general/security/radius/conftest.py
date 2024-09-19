import pytest


# @pytest.fixture(scope='session', autouse=True)
# def prepare_scp_test(prepare_scp):
#     return


@pytest.fixture(scope='function', autouse=True)
def recover_after_aaa(cleanup_after_aaa):
    return
