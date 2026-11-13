"""Never inherit workstation sign-in paths while running repository tests."""
import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home=tmp_path/'owner';home.mkdir(mode=0o700)
    monkeypatch.setenv('HOME',str(home))
    monkeypatch.delenv('CODEX_HOME',raising=False)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test may reach a provider: a sign-in reader that forgot its fake fails loudly instead."""
    import http.client
    def refuse(self,*args,**kwargs):raise AssertionError('network access in tests')
    monkeypatch.setattr(http.client.HTTPSConnection,'connect',refuse)
