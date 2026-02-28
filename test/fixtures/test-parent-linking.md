# TESTING md2jira -- Parent Linking Verification

This Epic tests explicit parent assignment via the {parent:KEY} inline syntax.

## TESTING md2jira -- Orphan Story (no explicit parent)

This Story has no {parent:KEY} annotation, so it links to the preceding Epic automatically.

## TESTING md2jira -- Story Under Foreign Epic {parent:WBA-1}

This Story uses an explicit {parent:KEY} annotation to link to an existing Epic.
Replace WBA-1 with a real Epic key in your project before running.

### TESTING md2jira -- Subtask With Explicit Parent {parent:WBA-2}

This Sub-task uses {parent:KEY} to link to a specific Story or Task.
Replace WBA-2 with a real Story/Task key before running.

### TESTING md2jira -- Subtask (auto-linked)

This Sub-task has no annotation, so it links to the most recently created/found Story above.
