# Luna

Look in `.agents/skills/` for project skills and apply those relevant to the task.

Put new or updated tests in `__tests__/`, mirroring the tested source file's
directory. For example, `install.sh` uses `__tests__/test_install.py`, while a
file in `scripts/` uses `__tests__/scripts/`. Move tests being updated to this
layout; keep the rest of the existing `tests/` files in place.

Keep user-facing logs concise: useful progress, actionable errors, and next steps.
Omit routine implementation metadata and long explanatory paragraphs.

Internal setup scripts ignore extra arguments and continue past noncritical
failures. Optional steps should warn and skip; essential dependencies and required
file operations must succeed.

Setup does not create automatic backups. Tell users to back up files they want
to keep before installation.
