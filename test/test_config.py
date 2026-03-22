"""Unit tests for config loading and resolution.

These tests verify that:
  - TOML config files are parsed correctly
  - Instance and project selection works
  - CLI args override env vars override config file
  - Backward-compatible .env-only mode still works
  - Errors are raised for ambiguous multi-instance configs
"""

import argparse
import os
import tempfile
import pytest
from unittest.mock import patch

from src.config import (
    load_config,
    _find_config_file,
    MD2JiraConfig,
    JiraInstanceConfig,
    JiraProjectConfig,
)


def _make_args(**overrides):
    defaults = {
        'INFILE': 'example.md',
        'JIRA_PROJECT_KEY': None,
        'instance': None,
        'config': None,
        'epic': None,
        'parent': None,
        'verbose': False,
        'dry_run': False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


SINGLE_INSTANCE_TOML = b"""
[instances.myorg]
subdomain = "myorg"
domain = "atlassian.net"
auth_key_env = "MY_AUTH_KEY"

  [instances.myorg.projects.ABC]
  epic_name_field = "customfield_99001"
  epic_link_field = "customfield_99002"
  team_field = "customfield_99003"
  team_value = "Alpha Team"
  checklist_field = "customfield_99004"
"""

MULTI_INSTANCE_TOML = b"""
[instances.org_a]
subdomain = "org-a"
auth_key_env = "AUTH_A"

  [instances.org_a.projects.PROJA]
  epic_name_field = "customfield_11111"
  epic_link_field = "customfield_11112"

[instances.org_b]
subdomain = "org-b"
auth_key_env = "AUTH_B"

  [instances.org_b.projects.PROJB]
  epic_name_field = "customfield_22221"
  epic_link_field = "customfield_22222"
"""


class TestFindConfigFile:
    def test_explicit_path_found(self, tmp_path):
        cfg = tmp_path / ".md2jira.toml"
        cfg.write_text("")
        assert _find_config_file(str(cfg)) == cfg

    def test_explicit_path_missing(self, tmp_path):
        assert _find_config_file(str(tmp_path / "nope.toml")) is None

    def test_no_path_no_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert _find_config_file() is None


class TestLoadConfigEnvOnly:
    """Backward-compatible mode: no config file, only env vars.

    Tests chdir to tmp_path so load_dotenv() does not pick up the
    real .env from the workspace root.
    """

    @patch('src.config.load_dotenv')
    def test_env_vars_populate_config(self, mock_dotenv, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        env = {
            'JIRA_PROJECT_SUBDOMAIN': 'testorg',
            'JIRA_DOMAIN': 'atlassian.net',
            'JIRA_AUTH_KEY': 'dW5zZXQ6dW5zZXQ=',
            'JIRA_PROJECT_KEY': 'TEST',
            'JIRA_CHECKLIST_CUSTOMFIELD': 'customfield_55555',
            'JIRA_WBA_TEAM': 'Bravo Team',
        }
        with patch.dict(os.environ, env, clear=False):
            config = load_config(_make_args())

        assert config.instance.subdomain == 'testorg'
        assert config.instance.domain == 'atlassian.net'
        assert config.instance.auth_key_env == 'JIRA_AUTH_KEY'
        assert config.project.project_key == 'TEST'
        assert config.project.checklist_field == 'customfield_55555'
        assert config.project.team_value == 'Bravo Team'
        assert config.project.team_field == 'customfield_10032'

    @patch('src.config.load_dotenv')
    def test_cli_project_overrides_env(self, mock_dotenv, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        env = {
            'JIRA_PROJECT_SUBDOMAIN': 'x',
            'JIRA_AUTH_KEY': 'x',
            'JIRA_PROJECT_KEY': 'FROM_ENV',
        }
        with patch.dict(os.environ, env, clear=False):
            config = load_config(_make_args(JIRA_PROJECT_KEY='FROM_CLI'))

        assert config.project.project_key == 'FROM_CLI'

    @patch('src.config.load_dotenv')
    def test_defaults_without_env_vars(self, mock_dotenv, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        env = {'JIRA_PROJECT_SUBDOMAIN': 'x'}
        with patch.dict(os.environ, env, clear=False):
            config = load_config(_make_args())

        assert config.instance.domain == 'atlassian.net'
        assert config.project.epic_name_field == 'customfield_10011'
        assert config.project.epic_link_field == 'customfield_10014'
        assert config.project.parent_field == 'parent'


class TestLoadConfigToml:
    """Config file mode with TOML."""

    def test_single_instance_auto_selected(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / ".md2jira.toml"
        cfg_file.write_bytes(SINGLE_INSTANCE_TOML)
        monkeypatch.chdir(tmp_path)

        env = {'MY_AUTH_KEY': 'test_key'}
        with patch.dict(os.environ, env, clear=False):
            config = load_config(_make_args(JIRA_PROJECT_KEY='ABC'))

        assert config.instance.subdomain == 'myorg'
        assert config.instance.auth_key_env == 'MY_AUTH_KEY'
        assert config.project.epic_name_field == 'customfield_99001'
        assert config.project.epic_link_field == 'customfield_99002'
        assert config.project.team_field == 'customfield_99003'
        assert config.project.team_value == 'Alpha Team'
        assert config.project.checklist_field == 'customfield_99004'

    def test_multi_instance_requires_selection(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / ".md2jira.toml"
        cfg_file.write_bytes(MULTI_INSTANCE_TOML)
        monkeypatch.chdir(tmp_path)

        with patch.dict(os.environ, {}, clear=False):
            with pytest.raises(ValueError, match="Multiple instances"):
                load_config(_make_args())

    def test_multi_instance_explicit_selection(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / ".md2jira.toml"
        cfg_file.write_bytes(MULTI_INSTANCE_TOML)
        monkeypatch.chdir(tmp_path)

        env = {'AUTH_B': 'key_b'}
        with patch.dict(os.environ, env, clear=False):
            config = load_config(_make_args(instance='org_b', JIRA_PROJECT_KEY='PROJB'))

        assert config.instance.subdomain == 'org-b'
        assert config.instance.auth_key_env == 'AUTH_B'
        assert config.project.epic_name_field == 'customfield_22221'

    def test_invalid_instance_name_raises(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / ".md2jira.toml"
        cfg_file.write_bytes(SINGLE_INSTANCE_TOML)
        monkeypatch.chdir(tmp_path)

        with patch.dict(os.environ, {}, clear=False):
            with pytest.raises(ValueError, match="not found"):
                load_config(_make_args(instance='nonexistent'))

    def test_explicit_config_path(self, tmp_path):
        cfg_file = tmp_path / "custom_config.toml"
        cfg_file.write_bytes(SINGLE_INSTANCE_TOML)

        env = {'MY_AUTH_KEY': 'test'}
        with patch.dict(os.environ, env, clear=False):
            config = load_config(_make_args(
                config=str(cfg_file),
                JIRA_PROJECT_KEY='ABC'
            ))

        assert config.instance.subdomain == 'myorg'
        assert config.project.epic_name_field == 'customfield_99001'

    def test_project_not_in_config_uses_defaults(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / ".md2jira.toml"
        cfg_file.write_bytes(SINGLE_INSTANCE_TOML)
        monkeypatch.chdir(tmp_path)

        env = {'MY_AUTH_KEY': 'test'}
        with patch.dict(os.environ, env, clear=False):
            config = load_config(_make_args(JIRA_PROJECT_KEY='UNKNOWN'))

        assert config.project.project_key == 'UNKNOWN'
        assert config.project.epic_name_field == 'customfield_10011'
        assert config.project.epic_link_field == 'customfield_10014'


class TestLoadConfigCLIFlags:
    @patch('src.config.load_dotenv')
    def test_epic_and_parent_flags(self, mock_dotenv, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        env = {'JIRA_PROJECT_SUBDOMAIN': 'x', 'JIRA_AUTH_KEY': 'x'}
        with patch.dict(os.environ, env, clear=False):
            config = load_config(_make_args(
                epic='PROJ-100',
                parent='PROJ-200',
            ))

        assert config.default_epic_key == 'PROJ-100'
        assert config.default_parent_key == 'PROJ-200'

    @patch('src.config.load_dotenv')
    def test_dry_run_flag(self, mock_dotenv, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        env = {'JIRA_PROJECT_SUBDOMAIN': 'x', 'JIRA_AUTH_KEY': 'x'}
        with patch.dict(os.environ, env, clear=False):
            config = load_config(_make_args(dry_run=True))

        assert config.dry_run is True

    @patch('src.config.load_dotenv')
    def test_verbose_flag(self, mock_dotenv, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        env = {'JIRA_PROJECT_SUBDOMAIN': 'x', 'JIRA_AUTH_KEY': 'x'}
        with patch.dict(os.environ, env, clear=False):
            config = load_config(_make_args(verbose=True))

        assert config.verbose is True
