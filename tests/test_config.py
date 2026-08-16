import pytest
import os
from pathlib import Path
from nanogateway.config import load_config, Settings


@pytest.fixture
def isolated_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_load_config_with_env_vars(monkeypatch, isolated_cwd):
    monkeypatch.setenv("NANOGATEWAY_URL", "https://test.openai.com/v1")
    config = load_config()
    assert config.url == "https://test.openai.com/v1"


def test_load_config_from_yaml(isolated_cwd, monkeypatch):
    config_file = isolated_cwd / "config.yaml"
    config_file.write_text("""
url: "https://yaml.openai.com/v1"
guardrails:
  injection:
    enabled: true
    action: block
""")
    config = load_config(str(config_file))
    assert config.url == "https://yaml.openai.com/v1"
    assert config.guardrails.injection.enabled is True


def test_load_config_defaults(isolated_cwd, monkeypatch):
    monkeypatch.delenv("NANOGATEWAY_URL", raising=False)
    config = load_config()
    assert config.url == "https://api.openai.com/v1"
    assert config.guardrails.injection.enabled is False
    assert config.guardrails.injection.action == "block"


def test_env_overrides_yaml(isolated_cwd, monkeypatch):
    config_file = isolated_cwd / "config.yaml"
    config_file.write_text('url: "https://yaml.openai.com/v1"\n')
    monkeypatch.setenv("NANOGATEWAY_URL", "https://env.openai.com/v1")
    config = load_config(str(config_file))
    assert config.url == "https://env.openai.com/v1"
