import pytest
from _pytest.monkeypatch import MonkeyPatch


@pytest.fixture(scope="session")
def monkeysession(request):
    mpatch = MonkeyPatch()
    yield mpatch
    mpatch.undo()


@pytest.fixture(scope="session", autouse=True)
def set_environment_vars(monkeysession):
    monkeysession.setenv("TEST_VARIABLE", "variable_test")
