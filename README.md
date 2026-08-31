# grammar-check

A GitHub Action that runs an LLM over your repo's prose files (`.tex`, `.md`, …) on every push, fixes grammar and spelling, and opens a PR with the changes.

Edits land in a PR for review instead of pushing straight to `main`, so you stay in control of what merges.

## Quick start

`.github/workflows/grammar.yml`:

```yaml
name: Grammar Check
on:
  push:
    branches: [main]

permissions:
  contents: write
  pull-requests: write

jobs:
  grammar:
    runs-on: ubuntu-latest
    steps:
      - uses: Mattschoe/grammar-check@v1
        with:
          provider: claude
          api-key: ${{ secrets.LLM_API_KEY }}
          file-extensions: tex,md
```

The action handles opening the PR.

## How it works

On each push, the action looks at which files changed, filters to the 
extensions you configured, and sends only those files to your chosen LLM. 
The model is instructed to fix grammar and spelling only, never markup, 
code, math, citations, or references. If anything was corrected, 
you get a PR with the cleaned-up files and a bullet summary of changes; 
if nothing needed fixing, the action is a no-op.

## Inputs

| Input               | Required | Default  | Description                                                   |
|---------------------|----------|----------|---------------------------------------------------------------|
| `provider`          | yes      | —        | `claude` or `deepseek`.                                       |
| `api-key`           | yes      | —        | API key for the chosen provider.                              |
| `file-extensions`   | yes      | —        | Comma-separated extensions to check, no dots (e.g. `tex,md`). |
| `tier`              | no       | `medium` | Model size: `cheap`, `medium`, or `expensive`.                |
| `max-output-tokens`    | no       | `16384`  | Max output tokens per file. Raise for long documents.         |
| `system-prompt-append` | no       | —        | Extra instructions appended to the LLM system prompt.         |
| `commit-message`    | no       | `fix: grammar and spelling fixes` | Commit message + PR title for the grammar-fix PR. Free-form; any message accepted. |

Example with extra instructions:

```yaml
with:
  system-prompt-append: |
    Avoid em-dashes — use commas or parentheses instead.
    Ensure the tone is formal academic English.
```

## Supported Providers & Tiers

- **Claude:**  `api-key` is your Anthropic key. Tiers map to Haiku 4.5 (`cheap`), Sonnet 4.6 (`medium`), and Opus 4.7 (`expensive`).
- **DeepSeek:** `api-key` is your DeepSeek key. `cheap` and `medium` use `deepseek-v4-flash`; `expensive` uses `deepseek-v4-pro` with extended thinking.

## Optional: skip pushes that don't touch prose

If you'd rather not invoke the action on pushes that don't touch any of the configured file types, add a `paths` filter that mirrors your `file-extensions`:

```yaml
on:
  push:
    branches: [main]
    paths: ['**.tex', '**.md']
```

This is purely an optimization, the action is already a no-op when no matching files changed.

## Permissions

The workflow needs `contents: write` and `pull-requests: write` so the final step can 
open a PR via `gh`. Without them you'll see a 403 from `gh pr create`.

To enable permissions go to: `Settings` -> `Actions` -> `General` 
-> `Workflow Permissions` -> `Allow GitHub Actions to create and approve pull requests`

## FAQ

**Will it edit my code, math, or markup?**
No. The model is told to leave LaTeX commands, Markdown syntax, code blocks, inline code, math, citations, and references untouched, and to only correct clear prose errors.

**Does merging a grammar-fix PR re-trigger the action?**
No. The action detects pushes that consist entirely of its own commits (by checking the commit author) and skips them automatically. This works with merge commits and rebase-and-merge. If you use squash-and-merge, add a job-level guard to your workflow: `if: github.event.head_commit.author.name != 'github-actions[bot]'`.

**Does it cost money?**
Yes, you're paying your LLM provider directly per request. Pick `cheap` if you're cost-sensitive, or `expensive` for the strongest model on each provider.

## Contributing

Issues and PRs welcome at [github.com/Mattschoe/grammar-check](https://github.com/Mattschoe/grammar-check).

## License

BSD 3-Clause — see [LICENSE](./LICENSE).
