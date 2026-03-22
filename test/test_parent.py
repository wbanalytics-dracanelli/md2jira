"""Unit tests for parent issue assignment.

These tests verify that:
  - {parent:KEY} inline syntax is extracted from headers
  - --epic / --parent CLI flags seed epic_id and parent_id
  - explicit_parent overrides sequential parent tracking in prepare_issue
  - Parent/epic-link changes are detected by diff_issue_against_remote
  - Minimal diff payloads include parent changes
"""

import json
import os
import pytest
from unittest.mock import patch

from src.config import MD2JiraConfig, JiraInstanceConfig, JiraProjectConfig
from src.md2jira import MD2Jira, Issue, IssueType


def _make_config(**overrides):
    defaults = dict(
        instance=JiraInstanceConfig(subdomain='fake', domain='atlassian.net'),
        project=JiraProjectConfig(
            project_key='TEST',
            epic_name_field='customfield_10011',
            epic_link_field='customfield_10014',
        ),
        infile='example.md',
        verbose=False,
        dry_run=False,
        default_epic_key=None,
        default_parent_key=None,
    )
    defaults.update(overrides)
    return MD2JiraConfig(**defaults)


def _make_md2jira(**config_overrides):
    env = {'JIRA_AUTH_KEY': 'dW5zZXQ6dW5zZXQ='}
    with patch.dict(os.environ, env, clear=False):
        return MD2Jira(_make_config(**config_overrides))


class TestExtractParent:
    def setup_method(self):
        self.md2j = _make_md2jira()

    def test_no_parent_annotation(self):
        parent, text = self.md2j._extract_parent('Story Title')
        assert parent is None
        assert text == 'Story Title'

    def test_parent_at_end(self):
        parent, text = self.md2j._extract_parent('Story Title {parent:EPIC-123}')
        assert parent == 'EPIC-123'
        assert text == 'Story Title'

    def test_parent_with_extra_whitespace(self):
        parent, text = self.md2j._extract_parent('Story Title  {parent:PROJ-99}  ')
        assert parent == 'PROJ-99'
        assert text == 'Story Title'

    def test_parent_not_at_end_ignored(self):
        parent, text = self.md2j._extract_parent('{parent:EPIC-1} Story Title')
        assert parent is None
        assert text == '{parent:EPIC-1} Story Title'

    def test_parent_with_lowercase_project(self):
        parent, text = self.md2j._extract_parent('Title {parent:proj-42}')
        assert parent == 'proj-42'
        assert text == 'Title'


class TestCLIParentSeeding:
    def test_epic_flag_seeds_epic_id(self):
        md2j = _make_md2jira(default_epic_key='PROJ-100')
        assert md2j.epic_id == 'PROJ-100'

    def test_parent_flag_seeds_parent_id(self):
        md2j = _make_md2jira(default_parent_key='PROJ-200')
        assert md2j.parent_id == 'PROJ-200'

    def test_no_flags_empty_ids(self):
        md2j = _make_md2jira()
        assert md2j.epic_id == ''
        assert md2j.parent_id == ''


class TestPrepareIssueParent:
    def setup_method(self):
        self.md2j = _make_md2jira()

    def test_create_task_uses_explicit_parent(self):
        self.md2j.epic_id = 'EPIC-OLD'
        issue = Issue(IssueType.Task, '', 'My Task', 'desc')
        issue.explicit_parent = 'EPIC-NEW'

        result = json.loads(self.md2j.prepare_issue(issue))
        assert result['fields']['customfield_10014'] == 'EPIC-NEW'

    def test_create_task_falls_back_to_epic_id(self):
        self.md2j.epic_id = 'EPIC-50'
        issue = Issue(IssueType.Task, '', 'My Task', 'desc')

        result = json.loads(self.md2j.prepare_issue(issue))
        assert result['fields']['customfield_10014'] == 'EPIC-50'

    def test_create_subtask_uses_explicit_parent(self):
        self.md2j.parent_id = 'TASK-OLD'
        issue = Issue(IssueType.Subtask, '', 'My Subtask', 'desc')
        issue.explicit_parent = 'TASK-NEW'

        result = json.loads(self.md2j.prepare_issue(issue))
        assert result['fields']['parent'] == {'key': 'TASK-NEW'}

    def test_create_subtask_falls_back_to_parent_id(self):
        self.md2j.parent_id = 'TASK-10'
        issue = Issue(IssueType.Subtask, '', 'My Subtask', 'desc')

        result = json.loads(self.md2j.prepare_issue(issue))
        assert result['fields']['parent'] == {'key': 'TASK-10'}

    def test_create_epic_no_parent_field(self):
        issue = Issue(IssueType.Epic, '', 'My Epic', 'desc')
        result = json.loads(self.md2j.prepare_issue(issue))
        assert 'parent' not in result['fields']
        assert 'customfield_10014' not in result['fields']


class TestPrepareIssueMinimalDiff:
    def setup_method(self):
        self.md2j = _make_md2jira()

    def test_no_changes_returns_none(self):
        local = Issue(IssueType.Epic, 'TEST-1', 'Epic', 'Same desc')
        remote = Issue(IssueType.Epic, 'TEST-1', 'Epic', 'Same desc')
        result = self.md2j.prepare_issue(local, updating=True, remote_issue=remote)
        assert result is None

    def test_summary_change_only(self):
        local = Issue(IssueType.Epic, 'TEST-1', 'New Title', 'Same desc')
        remote = Issue(IssueType.Epic, 'TEST-1', 'Old Title', 'Same desc')
        result = json.loads(self.md2j.prepare_issue(local, updating=True, remote_issue=remote))
        assert result['fields'] == {'summary': 'New Title'}

    def test_description_change_only(self):
        local = Issue(IssueType.Epic, 'TEST-1', 'Epic', 'new desc')
        remote = Issue(IssueType.Epic, 'TEST-1', 'Epic', 'old desc')
        result = json.loads(self.md2j.prepare_issue(local, updating=True, remote_issue=remote))
        assert 'description' in result['fields']
        assert 'summary' not in result['fields']

    def test_epic_link_change_included(self):
        self.md2j.epic_id = 'EPIC-NEW'
        local = Issue(IssueType.Task, 'TEST-2', 'Task', 'desc')
        remote = Issue(IssueType.Task, 'TEST-2', 'Task', 'desc')
        remote.epic_id = 'EPIC-OLD'
        result = json.loads(self.md2j.prepare_issue(local, updating=True, remote_issue=remote))
        assert result['fields']['customfield_10014'] == 'EPIC-NEW'

    def test_parent_change_included_for_subtask(self):
        self.md2j.parent_id = 'TASK-NEW'
        local = Issue(IssueType.Subtask, 'TEST-3', 'Sub', 'desc')
        remote = Issue(IssueType.Subtask, 'TEST-3', 'Sub', 'desc')
        remote.parent_id = 'TASK-OLD'
        result = json.loads(self.md2j.prepare_issue(local, updating=True, remote_issue=remote))
        assert result['fields']['parent'] == {'key': 'TASK-NEW'}


class TestDiffParentChanges:
    def setup_method(self):
        self.md2j = _make_md2jira()

    def test_epic_link_change_detected(self):
        self.md2j.epic_id = 'EPIC-NEW'
        local = Issue(IssueType.Task, 'TEST-1', 'Task', 'desc')
        remote = Issue(IssueType.Task, 'TEST-1', 'Task', 'desc')
        remote.epic_id = 'EPIC-OLD'
        assert self.md2j.diff_issue_against_remote(local, remote) is True

    def test_parent_change_detected_for_subtask(self):
        self.md2j.parent_id = 'TASK-NEW'
        local = Issue(IssueType.Subtask, 'TEST-1', 'Sub', 'desc')
        remote = Issue(IssueType.Subtask, 'TEST-1', 'Sub', 'desc')
        remote.parent_id = 'TASK-OLD'
        assert self.md2j.diff_issue_against_remote(local, remote) is True

    def test_no_change_when_parents_match(self):
        self.md2j.epic_id = 'EPIC-1'
        local = Issue(IssueType.Task, 'TEST-1', 'Task', 'desc')
        remote = Issue(IssueType.Task, 'TEST-1', 'Task', 'desc')
        remote.epic_id = 'EPIC-1'
        assert self.md2j.diff_issue_against_remote(local, remote) is False

    def test_explicit_parent_overrides_in_diff(self):
        self.md2j.epic_id = 'EPIC-SEQ'
        local = Issue(IssueType.Task, 'TEST-1', 'Task', 'desc')
        local.explicit_parent = 'EPIC-EXPLICIT'
        remote = Issue(IssueType.Task, 'TEST-1', 'Task', 'desc')
        remote.epic_id = 'EPIC-SEQ'
        assert self.md2j.diff_issue_against_remote(local, remote) is True


class TestDryRun:
    def test_dry_run_skips_api_calls(self, capsys):
        md2j = _make_md2jira(dry_run=True)
        issue = Issue(IssueType.Epic, '', 'Test Epic', 'desc')

        with patch.object(MD2Jira, 'find_issue') as mock_find, \
             patch.object(MD2Jira, 'create_issue') as mock_create:
            md2j.process_issue(issue)

        mock_find.assert_not_called()
        mock_create.assert_not_called()
        captured = capsys.readouterr()
        assert '[dry-run]' in captured.out
