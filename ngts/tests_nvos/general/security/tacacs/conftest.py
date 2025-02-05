import pytest


@pytest.fixture(scope='function', autouse=True)
def recover_after_aaa(cleanup_after_aaa):
    return
