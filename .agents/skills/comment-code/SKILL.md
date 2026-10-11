---
name: comment-code
description: Apply Luna's spacing, indentation, and meaningful-comment conventions when creating or editing code, scripts, or configuration, including readability-only edits.
---

# Code and Configuration Readability

Apply these conventions to new or modified work. Do not expand a small change
into an unrelated formatting or commenting pass across the repository.

## Spacing and layout

- Use four spaces for indentation in Luna's Bash and Lua code. Preserve an
  established convention in other languages and syntax-sensitive formats.
- Separate logical sections with one blank line. Within functions, separate
  distinct steps such as reading, validating, applying, and reporting.
- Place each section comment directly above its code, with a blank line before
  the combined comment-and-code block.
- Use spaces around operators and after commas where the language permits.
  Preserve Bash assignment syntax and whitespace inside strings or templates.
- Expand cramped branches and multiple shell operations onto separate lines.
  Keep closely related statements together; do not space out every statement.

## Meaningful comments

- Explain a file's role and how it is invoked when that context is not obvious.
- Introduce logical sections and functions with non-obvious responsibilities,
  side effects, or assumptions.
- Explain why decisions exist: bootstrap ordering, compatibility, precedence,
  persistence, path handling, and important constraints.
- Put explanations beside tricky validation, quoting, external calls, and
  failure handling. Describe customization points where useful.
- For configuration, explain meaningful units, accepted values, defaults, and
  interactions with overrides when a reader would otherwise have to guess.

Prefer short, concrete explanations over vague file headers. Do not impose a
comment quota or narrate obvious syntax. Avoid speculative claims and references
to abandoned approaches. Preserve useful comments and update them with behavior.

## Review before finishing

Check the changed sections for consistent spacing and indentation, comments next
to the relevant code, and comments that accurately describe actual behavior.
Use only comment syntax supported by the format; do not add comments to strict
JSON or introduce dependencies just to enable comments. Run applicable syntax
or behavior checks and describe their limits accurately.
