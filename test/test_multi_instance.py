"""Tests for multi-instance / multi-project configuration.

Unit tests (TestConfigResolution) run without credentials and verify
that the config file is parsed correctly for each instance+project
combination.

Live tests (TestLiveConnectivity) require valid credentials and verify
that md2jira can actually reach each configured Jira instance.  Run
them explicitly:

    pytest test/test_multi_instance.py -v -k "live"
"""

import json
import os
import argparse
import pytest
from unittest.mock import patch

from src.config import load_config, MD2JiraConfig, JiraInstanceConfig, JiraProjectConfig
from src.md2jira import MD2Jira, Issue, IssueType


CONFIG_FILE = os.path.join(os.path.dirname(__file__), '..', '.md2jira.toml')


def _make_args(**overrides):
    defaults = {
        'INFILE': 'example.md',
        'JIRA_PROJECT_KEY': None,
        'instance': None,
        'config': os.path.abspath(CONFIG_FILE),
        'epic': None,
        'parent': None,
        'verbose': False,
        'dry_run': False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# Unit tests -- config resolution (no credentials needed)
# ---------------------------------------------------------------------------

class TestConfigResolution:
    """Verify .md2jira.toml is parsed correctly for every instance+project."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_config(self):
        if not os.path.isfile(os.path.abspath(CONFIG_FILE)):
            pytest.skip(".md2jira.toml not found")

    @patch('src.config.load_dotenv')
    def test_wbinsights_wba(self, mock_dotenv):
        config = load_config(_make_args(instance='wbinsights', JIRA_PROJECT_KEY='WBA'))
        assert config.instance.subdomain == 'wbinsights'
        assert config.instance.auth_key_env == 'JIRA_AUTH_KEY'
        assert config.project.project_key == 'WBA'
        assert config.project.epic_name_field == 'customfield_10011'
        assert config.project.epic_link_field == 'customfield_10014'
        assert config.project.checklist_field == 'customfield_10078'

    @patch('src.config.load_dotenv')
    def test_wbinsights_cdp(self, mock_dotenv):
        config = load_config(_make_args(instance='wbinsights', JIRA_PROJECT_KEY='CDP'))
        assert config.instance.subdomain == 'wbinsights'
        assert config.project.project_key == 'CDP'
        assert config.project.epic_name_field == 'customfield_10011'
        assert config.project.checklist_field == 'customfield_10078'

    @patch('src.config.load_dotenv')
    def test_wbinsights_ts(self, mock_dotenv):
        config = load_config(_make_args(instance='wbinsights', JIRA_PROJECT_KEY='TS'))
        assert config.instance.subdomain == 'wbinsights'
        assert config.project.project_key == 'TS'
        assert config.project.epic_name_field == 'customfield_10011'
        assert config.project.checklist_field == 'customfield_10078'

    @patch('src.config.load_dotenv')
    def test_wbinsights_ci(self, mock_dotenv):
        config = load_config(_make_args(instance='wbinsights', JIRA_PROJECT_KEY='CI'))
        assert config.instance.subdomain == 'wbinsights'
        assert config.project.project_key == 'CI'
        assert config.project.epic_name_field == 'customfield_10011'
        assert config.project.checklist_field == 'customfield_10078'

    @patch('src.config.load_dotenv')
    def test_wbagora_es(self, mock_dotenv):
        config = load_config(_make_args(instance='wbagora', JIRA_PROJECT_KEY='ES'))
        assert config.instance.subdomain == 'wbagora'
        assert config.instance.auth_key_env == 'JIRA_AUTH_KEY'
        assert config.project.project_key == 'ES'
        assert config.project.epic_name_field == 'customfield_10020'
        assert config.project.epic_link_field == 'customfield_10018'
        assert config.project.checklist_field is None

    @patch('src.config.load_dotenv')
    def test_instance_selection_required(self, mock_dotenv):
        """With multiple instances, omitting --instance must raise."""
        with pytest.raises(ValueError, match="Multiple instances"):
            load_config(_make_args())

    @patch('src.config.load_dotenv')
    def test_prepare_issue_uses_project_fields(self, mock_dotenv):
        """Verify prepare_issue produces JSON with the right custom field IDs."""
        config = load_config(_make_args(instance='wbinsights', JIRA_PROJECT_KEY='CDP'))
        env = {'JIRA_AUTH_KEY': 'dW5zZXQ6dW5zZXQ='}
        with patch.dict(os.environ, env, clear=False):
            md2j = MD2Jira(config)
        md2j.epic_id = 'CDP-100'

        epic = Issue(IssueType.Epic, '', 'Test Epic', 'description')
        epic_json = json.loads(md2j.prepare_issue(epic))
        assert epic_json['fields']['customfield_10011'] == 'Test Epic'
        assert epic_json['fields']['project']['key'] == 'CDP'

        task = Issue(IssueType.Task, '', 'Test Task', 'description')
        task_json = json.loads(md2j.prepare_issue(task))
        assert task_json['fields']['customfield_10014'] == 'CDP-100'

    @patch('src.config.load_dotenv')
    def test_dry_run_with_each_project(self, mock_dotenv):
        """Dry run should work for every configured project."""
        for project in ['WBA', 'CDP', 'TS', 'CI']:
            config = load_config(_make_args(
                instance='wbinsights',
                JIRA_PROJECT_KEY=project,
                dry_run=True,
            ))
            assert config.dry_run is True
            assert config.project.project_key == project

    @patch('src.config.load_dotenv')
    def test_cache_files_scoped_per_project(self, mock_dotenv):
        """Each project should produce a distinct cache filename."""
        cache_files = set()
        env = {'JIRA_AUTH_KEY': 'dW5zZXQ6dW5zZXQ='}
        for project in ['WBA', 'CDP', 'TS', 'CI']:
            config = load_config(_make_args(
                instance='wbinsights', JIRA_PROJECT_KEY=project
            ))
            with patch.dict(os.environ, env, clear=False):
                md2j = MD2Jira(config)
            cache_files.add(md2j.cache_file)
        assert len(cache_files) == 4
        assert all('wbinsights' in f for f in cache_files)


# ---------------------------------------------------------------------------
# Live tests -- require credentials (run with: pytest -k "live")
# ---------------------------------------------------------------------------

class TestLiveConnectivity:
    """Verify live connectivity to each configured Jira instance.

    These tests create a temporary Epic, verify it exists, then delete it.
    They are skipped unless JIRA_AUTH_KEY is set and the instance is reachable.

    Run explicitly:
        pytest test/test_multi_instance.py -v -k "live"
    """

    @pytest.fixture(autouse=True)
    def _require_auth(self):
        from dotenv import load_dotenv
        load_dotenv(override=True)
        if not os.environ.get('JIRA_AUTH_KEY'):
            pytest.skip("JIRA_AUTH_KEY not set")

    @pytest.mark.parametrize("project,fixture", [
        ("WBA", None),
        ("CDP", "test/fixtures/test-cdp.md"),
        ("TS",  "test/fixtures/test-ts.md"),
        ("CI",  "test/fixtures/test-ci.md"),
    ])
    def test_live_wbinsights_create_delete(self, project, fixture):
        """Create a test Epic, verify it, then delete it."""
        config = load_config(_make_args(
            instance='wbinsights',
            JIRA_PROJECT_KEY=project,
        ))
        md2j = MD2Jira(config)

        summary = f'TESTING md2jira multi-instance -- {project} connectivity check'
        issue = Issue(IssueType.Epic, '', summary, 'Automated test issue. Safe to delete.')
        issue_data = md2j.prepare_issue(issue)

        created = md2j.create_issue(issue, issue_data)
        assert created is not None, f"Failed to create Epic in {project}"
        assert created.key.startswith(f'{project}-')

        deleted = md2j.delete_issue(created)
        assert deleted.status == 204, f"Failed to delete {created.key}"

    def test_live_wbagora_es_crud(self):
        """Full CRUD cycle against wbagora ES project."""
        config = load_config(_make_args(
            instance='wbagora',
            JIRA_PROJECT_KEY='ES',
        ))
        md2j = MD2Jira(config)

        summary = 'TESTING md2jira multi-instance -- wbagora ES CRUD'
        description = 'Automated CRUD test. Safe to delete.'
        issue = Issue(IssueType.Epic, '', summary, description)
        issue_data = md2j.prepare_issue(issue)

        created = md2j.create_issue(issue, issue_data)
        assert created is not None, "Failed to create Epic in ES"
        assert created.key.startswith('ES-'), f"Expected ES- prefix, got {created.key}"

        read_back = md2j.read_issue(created.key)
        assert read_back is not None, f"Failed to read {created.key}"
        assert read_back.summary == summary

        updated_desc = 'Updated description for CRUD test.'
        created.description = updated_desc
        update_data = md2j.prepare_issue(created)
        updated = md2j.update_issue(created, update_data)
        assert updated is not None, f"Failed to update {created.key}"

        read_updated = md2j.read_issue(created.key)
        assert read_updated.description == updated_desc

        deleted = md2j.delete_issue(created)
        assert deleted.status == 204, f"Failed to delete {created.key}"
