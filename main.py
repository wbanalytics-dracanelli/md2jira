import argparse
from src.config import load_config
from src import md2jira

def main():
    """MD2Jira: Convert Markdown into corresponding JIRA issues"""
    config = load_config(args)
    md2j = md2jira.MD2Jira(config)
    md2j.parse_markdown()

parser = argparse.ArgumentParser(description=main.__doc__)

parser.add_argument('-i', dest='INFILE', type=str, help='Input markdown file', required=True)
parser.add_argument('-p',
    dest='JIRA_PROJECT_KEY',
    help='"KEY" of target JIRA project',
    type=str
)
parser.add_argument('-n', '--instance',
    dest='instance',
    help='Name of Jira instance (from .md2jira.toml)',
    type=str
)
parser.add_argument('-c', '--config',
    dest='config',
    help='Path to .md2jira.toml config file',
    type=str
)
parser.add_argument('-e', '--epic',
    dest='epic',
    help='Parent epic key for all H2 issues (e.g. PROJ-123)',
    type=str
)
parser.add_argument('--parent',
    dest='parent',
    help='Parent key for all H3 issues (e.g. PROJ-456)',
    type=str
)
parser.add_argument('-t', '--task',
    dest='use_task_type',
    action='store_true',
    default=False,
    help='Create H2 (##) items as Jira "Task" issues instead of the default "Story"'
)
parser.add_argument('-d', '--dry-run',
    dest='dry_run',
    action='store_true',
    default=False,
    help='Preview changes without making API calls'
)
parser.add_argument('-v', '--verbose',
    action='store_true',
    default=False,
    help='Enable verbose output (show diff details during update detection)'
)
args = parser.parse_args()

if __name__=="__main__":
    main()
