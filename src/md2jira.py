#!/usr/bin/env python

import os
import shutil
import re
import tempfile
from enum import Enum
import urllib3
from urllib.parse import urlencode, quote
import certifi
import json
import hashlib

class MD2Jira:
    def __init__(self, config):

        self.config       = config
        self.PROJECT_KEY  = config.project.project_key

        self.baseurl      = f'https://{config.instance.subdomain}.{config.instance.domain}/rest/api/2'
        self.browse_url   = f'https://{config.instance.subdomain}.{config.instance.domain}/browse'
        self.http         = urllib3.PoolManager(ca_certs=certifi.where())
        self.epic_re      = re.compile(r'^#\s+')
        self.story_re     = re.compile(r'^##\s+')
        self.task_re      = re.compile(r'^##\s+')
        self.subtask_re   = re.compile(r'^###\s+')
        self.checklist_re = re.compile(r'^\* \[(.*)\] (.*)$')
        self.parent_re    = re.compile(r'\s*\{parent:([A-Za-z]+-\d+)\}\s*$')
        self.fence_re     = re.compile(r'^```(\w*)\s*$')
        self.inline_code_re = re.compile(r'`([^`]+)`')
        self.in_code_fence  = False
        self.epic_id      = config.default_epic_key or ''
        self.parent_id    = config.default_parent_key or ''

        self.checklist_custom_field = config.project.checklist_field
        self.checklist_enabled      = self.checklist_custom_field is not None
        self.verbose                = config.verbose
        self.dry_run                = config.dry_run

    def jira_http_call(self, url, verb='GET', body=''):

        req_headers={
            'Content-Type': 'application/json',
            'Authorization': 'Basic {}'.format(os.environ.get(self.config.instance.auth_key_env))
        }

        if verb == 'GET' or verb == 'DELETE':
            resp = self.http.request(verb, url, headers=req_headers)
        else:
            encoded_data = body.encode('utf-8')
            resp         = self.http.request(verb, url, headers=req_headers, body=encoded_data)
            if len(resp.data) > 0:
                json_loads   = json.loads(resp.data.decode('utf-8'))
                if 'errors' in json_loads:
                    for error in json_loads['errors']:
                        print('{}: {}'.format(error, json_loads['errors'][error]))

        return resp

    def create_issue(self, issue, issue_json):
        """Create new issue directly via JIRA 'issue' API"""
        url  = '{}/issue'.format(self.baseurl)
        resp = self.jira_http_call(url, 'POST', issue_json)
        json_loads = json.loads(resp.data.decode('utf-8'))
        errorMessages = json_loads['errorMessages'] if 'errorMessages' in json_loads else None
        errors = json_loads['errors'] if 'errors' in json_loads else None
        if errorMessages and len(errorMessages) > 0:
            print ('The following errors occurred:')
            print (f'{json_loads["errorMessages"][0]}')
        elif errors and len(errors) > 0:
            print ('The following errors occurred:')
            print (f'{json_loads["errors"]}')
        elif 'key' in json_loads:
            created_issue = Issue(
                IssueType.__dict__[issue.type.name.replace('-','')],
                json_loads['key'],
                issue.summary,
                issue.description,
                issue.checklist.text or ''

            )
            if issue.type is IssueType.Task and hasattr(issue, 'epic_id'):
                created_issue.epic_id = issue.epic_id
            if issue.type is IssueType.Subtask and hasattr(issue, 'parent_id'):
                created_issue.parent_id = issue.parent_id
            issue_key = json_loads['key']
            print (
                f'Created issue {issue_key}: {self.browse_url}/{issue_key}'
            )
            return created_issue
        return None

    def read_issue(self, issue_key): 
        """Read issue directly via JIRA 'issue' API"""
        fields = 'summary,description,priority,issuetype'
        if self.checklist_custom_field:
            fields += f',{self.checklist_custom_field}'
        url  = '{}/issue/{}?fields={}'.format(self.baseurl, issue_key, fields)
        resp = self.jira_http_call(url)
        json_loads = json.loads(resp.data.decode('utf-8'))
        if 'fields' in json_loads:
            fields = json_loads['fields']
            issue = Issue(
                IssueType.__dict__[fields['issuetype']['name'].replace('-','')],
                json_loads['key'],
                fields['summary'],
                fields['description'],
                fields.get(self.checklist_custom_field, '') if self.checklist_enabled else ''
            )
            return issue
        return None

    def update_issue(self, issue, issue_json):
        """Update existing issue directly via JIRA 'issue' API"""
        url  = '{}/issue/{}'.format(self.baseurl, issue.key)
        resp = self.jira_http_call(url, 'PUT', issue_json)
        if hasattr(resp, 'status') and resp.status == 204:
            updated_issue = Issue(
                IssueType.__dict__[issue.type.name.replace('-','')],
                issue.key,
                issue.summary,
                issue.description,
                issue.checklist.text
            )
            print("{} updated".format(issue.key))
            return updated_issue
        else:
            print("{} NOT updated".format(issue.key))
        return None

    def delete_issue(self, issue):
        """Delete issue directly via JIRA 'issue' API"""
        url  = '{}/issue/{}'.format(self.baseurl, issue.key)
        resp = self.jira_http_call(url, 'DELETE')
        return resp

    def find_issue(self, issue): 
        """Locate issue via JIRA 'search' API"""
        summary_encoded = issue.summary.replace('!','\\\\!')
        summary_encoded = summary_encoded.replace('-','\\\\-')
        
        epic_link_field = self.config.project.epic_link_field

        fetch_fields = 'summary,description,priority,issuetype,parent'
        fetch_fields += f',{epic_link_field}'
        if self.checklist_custom_field:
            fetch_fields += f',{self.checklist_custom_field}'
            
        # Use API v3 search/jql endpoint (v2 has been deprecated)
        api_v3_base = self.baseurl.replace('/rest/api/2', '/rest/api/3')
        url = f'{api_v3_base}/search/jql?jql=project={self.PROJECT_KEY}+AND+summary~"{summary_encoded.replace(" ", "+")}"&fields={fetch_fields}'
        
        resp        = self.jira_http_call(url)
        json_loads  = json.loads(resp.data.decode('utf-8'))
        found_issue = None

        if 'issues' in json_loads and len(json_loads['issues']) > 0:
            found_issues      = json_loads['issues']
            actual_issue_list = [i for i in found_issues if i['fields']['summary'] == issue.summary]
            if len(actual_issue_list) == 0:
                return None

            actual_issue      = actual_issue_list[0]
            key    = actual_issue['key']
            fields = actual_issue['fields']

            # Handle checklist field safely
            checklist_data = ""
            if self.checklist_custom_field and self.checklist_custom_field in fields:
                checklist_data = fields[self.checklist_custom_field]
    
            # More robust issue type mapping
            issue_type_name = fields['issuetype']['name']
            issue_type_clean = issue_type_name.replace('-','').replace(' ', '')
            
            # Try to find the matching IssueType
            try:
                issue_type = IssueType.__dict__[issue_type_clean]
            except KeyError:
                # Fallback for common mappings
                type_mapping = {
                    'SubTask': IssueType.Subtask,
                    'Task': IssueType.Task,
                    'Epic': IssueType.Epic,
                    'Story': IssueType.Story
                }
                issue_type = type_mapping.get(issue_type_clean, IssueType.Task)
            
            # Handle description field -- API v3 returns Atlassian Document
            # Format (ADF), a nested JSON dict, instead of wiki-markup text.
            description = fields.get('description', '')
            if isinstance(description, dict):
                description = self.adf_to_text(description)
            elif description is None:
                description = ''
                
            found_issue = Issue(
                issue_type,
                key,
                fields['summary'],
                description,
                checklist_data 
            )

            parent_data = fields.get('parent')
            if parent_data and isinstance(parent_data, dict) and 'key' in parent_data:
                found_issue.parent_id = parent_data['key']

            epic_link_data = fields.get(epic_link_field)
            if epic_link_data:
                found_issue.epic_id = epic_link_data

            return found_issue
        return None

    def _extract_parent(self, text):
        """Extract {parent:KEY} annotation from header text, return (parent_key, clean_text)."""
        match = self.parent_re.search(text)
        if match:
            parent_key = match.group(1)
            clean_text = self.parent_re.sub('', text).strip()
            return parent_key, clean_text
        return None, text

    def parse_markdown(self):
        fh           = open(self.config.infile, 'r', encoding='utf-8')
        lines        = fh.readlines()
        issues       = []
        issue_type   = IssueType.NONE
        parser_state = ParserState.DETECT_ISSUE
        summary      = None
        explicit_parent = None

        for line in lines:
            stripped   = line.strip()

            # Handle Markdown fenced code blocks. JIRA has no triple-backtick
            # syntax, so opening fences become {code:lang} / {code} and inner
            # lines are appended verbatim (no issue detection or inline
            # conversion) until the closing fence.
            fence_match = self.fence_re.match(stripped)
            if fence_match:
                if self.in_code_fence:
                    self.in_code_fence = False
                    issues[-1].description += '{code}\n'
                else:
                    self.in_code_fence = True
                    lang = fence_match.group(1)
                    open_tag = '{{code:{}}}'.format(lang) if lang else '{code}'
                    issues[-1].description += '{}\n'.format(open_tag)
                continue

            if self.in_code_fence:
                issues[-1].description += '{}\n'.format(line.rstrip('\n'))
                continue

            issue_type = self.detect_issue(stripped)
            explicit_parent = None

            if issue_type is IssueType.Epic:
                raw = re.sub(self.epic_re, '', stripped)
                explicit_parent, summary = self._extract_parent(raw)
                stripped = 'EPIC FOUND: {}'.format(summary)
            elif issue_type is IssueType.Task:
                raw = re.sub(self.task_re, '', stripped)
                explicit_parent, summary = self._extract_parent(raw)
                stripped = 'STORY FOUND: {}'.format(summary)
            elif issue_type is IssueType.Subtask:
                raw = re.sub(self.subtask_re, '', stripped)
                explicit_parent, summary = self._extract_parent(raw)
                stripped = 'Subtask FOUND: {}'.format(summary)

            if parser_state is ParserState.DETECT_ISSUE and issue_type in [IssueType.Epic, IssueType.Task, IssueType.Subtask]:
                new_issue = Issue(issue_type, '', summary)
                new_issue.explicit_parent = explicit_parent
                issues.append(new_issue)
                parser_state = ParserState.COLLECT_DESCRIPTION

            elif parser_state is ParserState.COLLECT_DESCRIPTION:

                if issue_type is IssueType.Checklist:
                    if hasattr(issues[-1], 'checklist') is False:
                        issues[-1].checklist = Checklist()
                    matches = re.match(self.checklist_re, stripped)
                    status, item_text = matches.group(1, 2)
                    item   = ChecklistItem(item_text, status)
                    issues[-1].checklist.append(item)

                elif issue_type is IssueType.NONE:
                    issues[-1].description += '{}\n'.format(self.md2wiki(stripped))

                else:
                    self.process_issue(issues[-1])
                    new_issue = Issue(issue_type, '', summary)
                    new_issue.explicit_parent = explicit_parent
                    issues.append(new_issue)

        # Process final issue
        self.process_issue(issues[-1])
        fh.close()

    def detect_issue(self, _str):
        issue_type = IssueType.NONE

        if self.epic_re.match(_str):
            issue_type = IssueType.Epic
        elif self.task_re.match(_str):
            issue_type = IssueType.Task
        elif self.subtask_re.match(_str):
            issue_type = IssueType.Subtask
        elif self.checklist_enabled and self.checklist_re.match(_str):
            issue_type = IssueType.Checklist

        return issue_type

    def process_issue(self, issue):
        if self.dry_run:
            print("[dry-run] Would process: {} ({})".format(issue.summary, issue.type.name))
            if issue.type is IssueType.Epic:
                self.epic_id = 'DRY-RUN-EPIC'
            if issue.type is IssueType.Task:
                self.parent_id = 'DRY-RUN-TASK'
            return

        remote_issue = self.find_issue(issue)
        if remote_issue != None:
            if remote_issue.type is IssueType.Epic:
                self.epic_id = remote_issue.key
            if remote_issue.type is IssueType.Task:
                self.parent_id = remote_issue.key
            issue.key = remote_issue.key
            issue.type = remote_issue.type

            # Primary change detection: compare local content hash against
            # the cache of what was last synced.  This avoids false positives
            # caused by JIRA API v3 returning descriptions in ADF format
            # (which can never match the original wiki-markup text).
            local_hash = self.generate_issue_hash(issue)
            if self.check_issue_cache_hash(issue.key, local_hash):
                if self.verbose:
                    print("  [cache-hit] hash {} unchanged".format(local_hash))
                print("{}: \"{}\" up to date, skipping".format(issue.key, issue.summary))
                return

            if self.verbose:
                print("  [cache-miss] {} not in cache or hash differs, comparing against remote".format(issue.key))

            # Fallback: if the issue is not in the cache (first run, cache
            # cleared, etc.), compare against the remote issue directly.
            issue_changed = self.diff_issue_against_remote(issue, remote_issue)
            if issue_changed is True:
                issue_data = self.prepare_issue(issue, updating=True, remote_issue=remote_issue)
                if issue_data is not None:
                    self.update_issue(issue, issue_data)
                self.update_issue_cache(issue)
            else:
                # Content matches remote -- seed the cache so future runs
                # can use the fast-path above.
                self.update_issue_cache(issue)
                print("{}: \"{}\" up to date, skipping".format(issue.key, issue.summary))
        else:
            issue_data   = self.prepare_issue(issue)
            create_issue = self.create_issue(issue, issue_data)

            if create_issue is not None:
                if create_issue is not None and create_issue.type is IssueType.Epic:
                    self.epic_id   = create_issue.key
                if create_issue is not None and create_issue.type is IssueType.Task:
                    self.parent_id = create_issue.key
                self.update_issue_cache(create_issue)
            else:
                print('ERROR: unable to create "{}"'.format(issue.summary))

    def diff_issue_against_remote(self, issue, remote_issue):
        """Determine if remote issue has changed since last local edit.

        Returns True when the local issue content differs from the remote
        issue, meaning an update API call is warranted.

        Note: the remote description may have been converted from ADF to
        plain text by adf_to_text(), so an exact character-for-character
        match is not always possible.  We normalise both sides (strip
        whitespace, collapse blank lines) before comparing.
        """
        changes = []

        if issue.summary != remote_issue.summary:
            changes.append('summary')

        local_desc  = self._normalise_for_compare(issue.description)
        remote_desc = self._normalise_for_compare(remote_issue.description or '')
        if local_desc != remote_desc:
            changes.append('description')

        local_cl  = (issue.checklist.text or '').strip()
        remote_cl = (remote_issue.checklist.text or '').strip()
        if local_cl != remote_cl:
            changes.append('checklist')

        explicit_parent = getattr(issue, 'explicit_parent', None)
        if issue.type is IssueType.Task:
            desired_epic = explicit_parent or self.epic_id
            current_epic = getattr(remote_issue, 'epic_id', None) or ''
            if desired_epic and desired_epic != current_epic:
                changes.append('epic_link')
        elif issue.type is IssueType.Subtask:
            desired_parent = explicit_parent or self.parent_id
            current_parent = getattr(remote_issue, 'parent_id', None) or ''
            if desired_parent and desired_parent != current_parent:
                changes.append('parent')

        if changes and self.verbose:
            print("  [diff] {} changed: {}".format(
                issue.key or issue.summary, ', '.join(changes)))

        return len(changes) > 0

    @staticmethod
    def _normalise_for_compare(text):
        """Normalise a description string for comparison.

        Strips leading/trailing whitespace, collapses runs of blank lines
        into a single newline, and strips trailing whitespace from each line.
        """
        if not text:
            return ''
        lines = [l.rstrip() for l in text.strip().splitlines()]
        # Collapse consecutive blank lines into one
        normalised = []
        prev_blank = False
        for line in lines:
            if line == '':
                if not prev_blank:
                    normalised.append(line)
                prev_blank = True
            else:
                normalised.append(line)
                prev_blank = False
        return '\n'.join(normalised)

    def prepare_issue(self, issue, updating=False, remote_issue=None):
        """Prepare JSON data to send to JIRA API.

        When updating with a remote_issue, produces a minimal diff payload
        containing only fields that actually changed.  Returns None if
        updating and no managed fields differ.
        """
        cfg = self.config.project
        explicit_parent = getattr(issue, 'explicit_parent', None)

        if updating and remote_issue:
            fields = {}

            if issue.summary != remote_issue.summary:
                fields['summary'] = issue.summary

            local_desc = issue.description.strip()
            remote_desc = self._normalise_for_compare(remote_issue.description or '')
            if self._normalise_for_compare(local_desc) != remote_desc:
                fields['description'] = local_desc

            if self.checklist_enabled and hasattr(issue, 'checklist') and len(issue.checklist.items) > 0:
                local_cl = (issue.checklist.text or '').strip()
                remote_cl = (remote_issue.checklist.text or '').strip()
                if local_cl != remote_cl:
                    fields[self.checklist_custom_field] = self.format_checklist(issue.checklist)

            if issue.type is IssueType.Task:
                desired_epic = explicit_parent or self.epic_id
                remote_epic = getattr(remote_issue, 'epic_id', None) or ''
                if desired_epic and desired_epic != remote_epic:
                    fields[cfg.epic_link_field] = desired_epic
            elif issue.type is IssueType.Subtask:
                desired_parent = explicit_parent or self.parent_id
                remote_parent = getattr(remote_issue, 'parent_id', None) or ''
                if desired_parent and desired_parent != remote_parent:
                    fields[cfg.parent_field] = {'key': desired_parent}

            if not fields:
                return None
            return json.dumps({'fields': fields})

        # Full payload for issue creation
        project_key = self.PROJECT_KEY
        issue_type = 'Sub-task' if issue.type is IssueType.Subtask else issue.type.name

        out_json = {
            'fields': {
                'project': {
                    'key': project_key
                },
                'summary': issue.summary,
                'description': issue.description.strip(),
                'issuetype': {
                    'name': issue_type
                }
            }
        }

        if issue.type is IssueType.Epic:
            out_json['fields'][cfg.epic_name_field] = issue.summary

        if issue.type is IssueType.Task:
            link_key = explicit_parent or self.epic_id
            if link_key:
                out_json['fields'][cfg.epic_link_field] = link_key

        if issue.type is IssueType.Subtask:
            parent_key = explicit_parent or self.parent_id
            if parent_key:
                out_json['fields'][cfg.parent_field] = {'key': parent_key}

        if cfg.team_field and cfg.team_value:
            out_json['fields'][cfg.team_field] = {
                'value': cfg.team_value
            }

        if hasattr(issue, 'checklist') and len(issue.checklist.items) > 0:
            if self.checklist_enabled is False:
                for item in issue.checklist.items:
                    out_json['fields']['description'] += '\n{}'.format(item.text)
            else:
                checklist_text = self.format_checklist(issue.checklist)
                out_json['fields'][self.checklist_custom_field] = checklist_text

        return json.dumps(out_json)

    def adf_to_text(self, adf):
        """Extract plain text from an Atlassian Document Format (ADF) dict.

        JIRA API v3 returns descriptions as ADF -- a nested JSON structure.
        This method recursively walks the tree and concatenates all text
        nodes, inserting newlines between block-level elements so that the
        result is comparable to the original wiki-markup description.
        """
        if adf is None:
            return ''
        if isinstance(adf, str):
            return adf

        parts = []
        node_type = adf.get('type', '')

        # Leaf text node
        if node_type == 'text':
            return adf.get('text', '')

        # Recurse into children
        for child in adf.get('content', []):
            parts.append(self.adf_to_text(child))

        # Block-level *containers* (whose children are themselves blocks)
        # get newline separators.  Inline containers like paragraph and
        # heading hold text nodes that should be concatenated directly.
        separator = '\n' if node_type in (
            'doc', 'blockquote',
            'bulletList', 'orderedList', 'listItem',
            'table', 'tableRow', 'tableCell', 'tableHeader',
            'mediaSingle',
        ) else ''

        return separator.join(parts)

    def md2wiki(self, _str):
        """Convert certain markdown to JIRA Wiki format"""
        text_replacements = {
            'link': {
                'match': re.compile(r'^(.*)\[([^\]]+)\]\(([^\)]+)\)(.*)$'),
                'pattern': re.compile(r'\[([^\]]+)\]\(([^)]+)\)'),
                'replacement': r'[\1|\2]'
            }
        }

        for _token_type, _replacement_info in text_replacements.items():
            _match, _pattern, _replacement = _replacement_info.values()
            matches = re.match(_match, _str)
            if matches is not None:
                _str = _pattern.sub(_replacement, _str)

        # Convert Markdown inline code (`text`) to JIRA monospace ({{text}}).
        # JIRA wiki markup renders backticks literally, so without this the
        # backtick characters show up verbatim in the rendered issue.
        _str = self.inline_code_re.sub(r'{{\1}}', _str)

        return _str

    def wiki2md(self, issue):
        """Convert JIRA issue to Markdown"""
        output = []
        # Print Summmary w/ right header level based on IssueType
        issue_type_value      = issue.type.value
        issue_type_header_str = '#' * issue_type_value
        output.append('{} {}\n'.format(issue_type_header_str, issue.summary).rstrip())

        # Print description
        output.append('{}\n'.format(issue.description))

        # Print formatted checklist if exists
        items = issue.checklist and issue.checklist.items
        if items and len(items) > 0:
            for item in items:
                status = item.status.name
                output.append('* [{}] {}'.format(item.reverse_mapping[status], item.text))
            
        # Overwrite original file, backing up original

        result = '\n'.join(output) 

        print(result)

        return result


    def format_checklist(self, checklist):
        # @see https://is.gd/uhaViF
        '''
        # Default checklist
        * [open] Checklist Item A
        * [in progress] Checklist Item B
        * [done] Checklist Item C
        '''
        output = '# Default Checklist\n' # raw format


        for item in checklist.items:
            status = item.status.name.lower().replace('_', ' ')
            output += '* [{}] {}\n'.format(status, item.text)

        return output

    def generate_issue_hash(self, issue): 
        explicit_parent = getattr(issue, 'explicit_parent', None) or ''
        parent_ctx = explicit_parent
        if not parent_ctx:
            if issue.type is IssueType.Task:
                parent_ctx = self.epic_id
            elif issue.type is IssueType.Subtask:
                parent_ctx = self.parent_id
            else:
                parent_ctx = ''
        hash_input = '{}:{}:{}:{}'.format(
            issue.summary, issue.description.strip(),
            issue.checklist.text.strip(), parent_ctx
        )
        result = hashlib.md5(hash_input.encode())
        return result.hexdigest()

    @property
    def cache_file(self):
        subdomain = self.config.instance.subdomain or 'default'
        project = self.PROJECT_KEY or 'default'
        return f'.md2jira_cache_{subdomain}_{project}.tsv'

    def check_issue_cache_hash(self, issue_key, issue_hash):
        result = False
        if os.path.exists(self.cache_file) is False:
            open(self.cache_file, 'a', encoding='utf-8').close()

        with open(self.cache_file, 'r', encoding='utf-8') as fh:
            for line in fh:
                key, summary, hash = '{}'.format(line.rstrip()).split('\t')
                if key == issue_key: 
                    result = (hash == issue_hash)
        return result

    def update_issue_cache(self, issue): 
        hash = self.generate_issue_hash(issue)
        if self.check_issue_cache_hash(issue.key, hash) is False:
            tmpfile = tempfile.NamedTemporaryFile(delete=False)
            with open(self.cache_file, 'r') as fh:
                for line in fh:
                    if line.startswith(issue.key) is False:
                        tmpfile.write(bytes(line,'utf-8'))

                fields = [issue.key, '"{}"'.format(issue.summary), hash]
                tmpfile.write(bytes('{}\n'.format('\t'.join(fields)), 'utf-8'))
                shutil.copyfile(tmpfile.name, '{}/{}'.format(os.getcwd(), self.cache_file))

class Issue:
    def __init__(self, type, key='', summary='', description='', checklist_text=''):
        self.key            = key 
        self.type           = type
        self.summary        = summary
        self.description    = description and description.strip()
        self.checklist      = Checklist(checklist_text)
        self.checklist_re   = re.compile(r'^.*\* \[(.*)\] (.*)$')
        self.epic_id          = None
        self.parent_id        = None
        self.explicit_parent  = None
        self.priority         = None
        self.assignee         = None

        if checklist_text is None:
            checklist_text = ''

        # Only process checklist if it's a string (not a dict from Jira API)
        if checklist_text and len(str(checklist_text)) > 0 and isinstance(checklist_text, str): 
            self.checklist = self.process_checklist(checklist_text)

    def process_checklist(self, str):
        """Convert checklist str in to checklist"""

        # Ignore first line, which is just name of the checklist
        for item in str.rstrip().split('\n')[1:]:
            matches = re.match(self.checklist_re, item.rstrip())
            status, item_text = matches.group(1, 2)
            checklist_item   = ChecklistItem(item_text, status)
            self.checklist.append(checklist_item)

        return self.checklist

class IssueType(Enum):
    NONE      = 0
    Epic      = 1
    Story     = 2
    Task      = 3
    Subtask   = 4
    SubTask   = 5
    Checklist = 6
    WBAAccessRequest = 7
    Defect = 8

class ParserState(Enum):
    NONE                = 0
    DETECT_ISSUE        = 1
    COLLECT_DESCRIPTION = 2
    COLLECT_CHECKLIST   = 3

class Checklist:
    def __init__(self, str):
        self.items  = []
        self.text   = str
    def __repr__(self):
        result = MD2Jira.format_checklist(self, self)
        return result
    def append(self, item):
        self.items.append(item)
        self.text = repr(self)

class ChecklistItem:
        
    def __init__(self, text, status):

        if status == '' or len(status) == 0:
            status = ' '

        self.shorthand_mapping = {
            'x': 'DONE',
            ' ': 'OPEN',
            '>': 'IN_PROGRESS'
        }

        self.reverse_mapping = {}
        for v in self.shorthand_mapping:
            self.reverse_mapping[self.shorthand_mapping[v]] = v

        self.text    = text
        self.status  = ChecklistItemStatus.__dict__[self.shorthand_mapping[status].upper() if status in self.shorthand_mapping.keys() else status.replace(' ', '_').upper()]
        try: 
            self.checked = self.status == ChecklistItemStatus.DONE
        except:
            print ('yay')

class ChecklistItemStatus(Enum):

    NONE        = 0
    OPEN        = 1
    IN_PROGRESS = 2
    SKIPPED     = 3
    DONE        = 4