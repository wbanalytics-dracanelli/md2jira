#!/usr/bin/env python

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


@dataclass
class JiraInstanceConfig:
    """Connection details for a single Jira Cloud site."""
    subdomain: str
    domain: str = "atlassian.net"
    auth_key_env: str = "JIRA_AUTH_KEY"


@dataclass
class JiraProjectConfig:
    """Custom field mappings for a specific project within a Jira instance."""
    project_key: str
    epic_name_field: str = "customfield_10011"
    epic_link_field: str = "customfield_10014"
    team_field: str | None = None
    team_value: str | None = None
    checklist_field: str | None = None
    parent_field: str = "parent"
    h2_issue_type: str = "Story"


@dataclass
class MD2JiraConfig:
    """Fully resolved configuration for an md2jira run."""
    instance: JiraInstanceConfig
    project: JiraProjectConfig
    infile: str = ""
    verbose: bool = False
    dry_run: bool = False
    default_epic_key: str | None = None
    default_parent_key: str | None = None


def _find_config_file(explicit_path: str | None = None) -> Path | None:
    """Locate .md2jira.toml, checking explicit path, CWD, then home dir."""
    if explicit_path:
        p = Path(explicit_path)
        return p if p.is_file() else None
    candidates = [
        Path.cwd() / ".md2jira.toml",
        Path.home() / ".md2jira.toml",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _load_toml(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_config(args) -> MD2JiraConfig:
    """Build MD2JiraConfig by merging TOML file, env vars, and CLI args.

    Resolution order (highest precedence wins):
      CLI flags > env vars > config file > built-in defaults
    """
    load_dotenv(override=True)

    config_path = _find_config_file(getattr(args, 'config', None))
    toml_data = _load_toml(config_path) if config_path else {}
    instances = toml_data.get("instances", {})

    instance_name = getattr(args, 'instance', None)
    instance_data = {}

    if instance_name and instance_name in instances:
        instance_data = instances[instance_name]
    elif instance_name and instance_name not in instances:
        available = ", ".join(instances.keys()) or "(none)"
        raise ValueError(
            f"Instance '{instance_name}' not found in config. "
            f"Available: {available}"
        )
    elif len(instances) == 1:
        instance_name = next(iter(instances))
        instance_data = instances[instance_name]
    elif len(instances) > 1:
        available = ", ".join(instances.keys())
        raise ValueError(
            f"Multiple instances configured ({available}). "
            f"Use --instance / -n to select one."
        )

    subdomain = (
        instance_data.get("subdomain")
        or os.environ.get("JIRA_PROJECT_SUBDOMAIN", "")
    )
    domain = (
        instance_data.get("domain")
        or os.environ.get("JIRA_DOMAIN", "atlassian.net")
    )
    auth_key_env = instance_data.get("auth_key_env", "JIRA_AUTH_KEY")

    instance_config = JiraInstanceConfig(
        subdomain=subdomain,
        domain=domain,
        auth_key_env=auth_key_env,
    )

    project_key = (
        getattr(args, 'JIRA_PROJECT_KEY', None)
        or os.environ.get("JIRA_PROJECT_KEY", "")
    )

    projects = instance_data.get("projects", {})
    project_data = projects.get(project_key, {})

    # Env var fallbacks only apply when there's no TOML config at all
    # (backward compat for single-instance .env-only users).
    # When a TOML instance exists, env vars for project-specific fields
    # (checklist, team) may belong to a different instance and must not
    # bleed through.
    has_toml_config = bool(instances)

    if has_toml_config:
        team_field = project_data.get("team_field")
        team_value = project_data.get("team_value")
        checklist_field = project_data.get("checklist_field")
    else:
        checklist_field = os.environ.get("JIRA_CHECKLIST_CUSTOMFIELD")
        team_value = os.environ.get("JIRA_WBA_TEAM")
        team_field = None
        if team_value:
            team_field = "customfield_10032"

    if team_value and not team_field:
        team_field = "customfield_10032"

    # H2 (##) Jira issue type: CLI --task flag forces "Task"; otherwise use
    # the per-project TOML value or the built-in "Story" default.
    if getattr(args, 'use_task_type', False):
        h2_issue_type = "Task"
    else:
        h2_issue_type = project_data.get("h2_issue_type") or "Story"

    project_config = JiraProjectConfig(
        project_key=project_key,
        epic_name_field=project_data.get("epic_name_field", "customfield_10011"),
        epic_link_field=project_data.get("epic_link_field", "customfield_10014"),
        team_field=team_field,
        team_value=team_value,
        checklist_field=checklist_field,
        parent_field=project_data.get("parent_field", "parent"),
        h2_issue_type=h2_issue_type,
    )

    return MD2JiraConfig(
        instance=instance_config,
        project=project_config,
        infile=getattr(args, 'INFILE', ''),
        verbose=getattr(args, 'verbose', False),
        dry_run=getattr(args, 'dry_run', False),
        default_epic_key=getattr(args, 'epic', None),
        default_parent_key=getattr(args, 'parent', None),
    )
