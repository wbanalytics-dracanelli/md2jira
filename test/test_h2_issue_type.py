"""Unit tests for the H2 (##) Jira issue type emitted by prepare_issue.

These tests are fully offline: they construct an MD2JiraConfig directly and
inspect the JSON payload produced by prepare_issue without making any API
calls.
"""

import json

from src.md2jira import MD2Jira, Issue, IssueType
from src.config import MD2JiraConfig, JiraInstanceConfig, JiraProjectConfig


def _make_md2jira(h2_issue_type="Story"):
    config = MD2JiraConfig(
        instance=JiraInstanceConfig(subdomain="example"),
        project=JiraProjectConfig(
            project_key="PROJ",
            h2_issue_type=h2_issue_type,
        ),
    )
    return MD2Jira(config)


def _issuetype_name(payload):
    return json.loads(payload)["fields"]["issuetype"]["name"]


class TestH2IssueTypePayload:
    def test_default_h2_is_story(self):
        md2jira = _make_md2jira()
        issue = Issue(IssueType.Task, '', 'H2 Item', 'desc')
        payload = md2jira.prepare_issue(issue)
        assert _issuetype_name(payload) == 'Story'

    def test_task_override_emits_task(self):
        md2jira = _make_md2jira(h2_issue_type="Task")
        issue = Issue(IssueType.Task, '', 'H2 Item', 'desc')
        payload = md2jira.prepare_issue(issue)
        assert _issuetype_name(payload) == 'Task'

    def test_epic_unaffected(self):
        md2jira = _make_md2jira(h2_issue_type="Task")
        issue = Issue(IssueType.Epic, '', 'Epic Item', 'desc')
        payload = md2jira.prepare_issue(issue)
        assert _issuetype_name(payload) == 'Epic'

    def test_subtask_unaffected(self):
        md2jira = _make_md2jira(h2_issue_type="Task")
        issue = Issue(IssueType.Subtask, '', 'Subtask Item', 'desc')
        payload = md2jira.prepare_issue(issue)
        assert _issuetype_name(payload) == 'Sub-task'
