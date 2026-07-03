"""Unit tests for config, errors, doctor, logging."""
import json
import os
import sys
import pytest
from pathlib import Path

from advancement_machine.config import ConfigManager, AppConfig
from advancement_machine.errors import AdvError, ConfigError, PluginLoadError, NetworkError, ErrorCategory
from advancement_machine.logging import setup_logging
from advancement_machine.doctor import Doctor

def test_config_defaults():
    cfg = ConfigManager.get()
    assert cfg.log_level == "INFO"
    assert cfg.log_dir == "./logs"
    assert isinstance(cfg, AppConfig)

def test_config_env_override(monkeypatch):
    monkeypatch.setenv("ADVANCEMENT_LOG_LEVEL", "DEBUG")
    ConfigManager._instance = None
    cfg = ConfigManager.get()
    assert cfg.log_level == "DEBUG"

def test_adv_error():
    e = AdvError(ErrorCategory.RUNTIME, "TEST_ERR", "Something went wrong", "Restart")
    d = e.to_dict()
    assert d["category"] == "runtime_error"
    assert d["code"] == "TEST_ERR"
    assert d["user_message"] == "Something went wrong"

def test_config_error():
    e = ConfigError("Bad config")
    assert e.category == ErrorCategory.CONFIG

def test_plugin_load_error():
    e = PluginLoadError("shady_plugin", "Module not found")
    assert "shady_plugin" in str(e)

def test_network_error():
    e = NetworkError("Connection refused")
    assert e.category == ErrorCategory.NETWORK

def test_doctor_runs():
    d = Doctor()
    report = d.run()
    assert report["app"] == "Advancement Machine"
    assert report["healthy"] is True
    assert "platform" in report

def test_logging_initializes():
    log = setup_logging()
    assert log.name == "Advancement Machine"