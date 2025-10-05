import importlib
import pytest

@pytest.mark.usefixtures("reset_config_module")
def test_google_workspace_mail_defaults(monkeypatch):
    monkeypatch.setenv("MAIL_PROVIDER", "google_workspace")
    for key in ["MAIL_SERVER", "MAIL_PORT", "MAIL_USE_TLS", "MAIL_USE_SSL"]:
        monkeypatch.delenv(key, raising=False)

    config_module = importlib.import_module("config")
    importlib.reload(config_module)

    assert config_module.Config.MAIL_SERVER == "smtp.gmail.com"
    assert config_module.Config.MAIL_PORT == 465
    assert config_module.Config.MAIL_USE_TLS is False
    assert config_module.Config.MAIL_USE_SSL is True


@pytest.fixture
def reset_config_module(monkeypatch):
    monkeypatch.delenv("MAIL_PROVIDER", raising=False)
    monkeypatch.delenv("MAIL_SERVER", raising=False)
    monkeypatch.delenv("MAIL_PORT", raising=False)
    monkeypatch.delenv("MAIL_USE_TLS", raising=False)
    monkeypatch.delenv("MAIL_USE_SSL", raising=False)
    import sys

    sys.modules.pop("config", None)
    yield
    sys.modules.pop("config", None)