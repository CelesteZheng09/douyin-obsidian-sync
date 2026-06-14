---
name: douyin-obsidian-sync
description: Configure, run, troubleshoot, and schedule the Douyin Favorites to Obsidian project. Use when a user wants to sync a named private Douyin favorite folder into a chosen Obsidian Vault directory, change the sync folder or destination, set a daily/weekly/hourly schedule, refresh Douyin login state, verify incremental transcript extraction, or repair this repository's local automation.
---

# Douyin Obsidian Sync

Operate the local-first pipeline in this repository. Keep cookies, API keys, media, state, and private notes out of Git.

## Locate The Project

Find the nearest ancestor containing both `pipeline/` and `config.example.yaml`. Treat it as `<project-root>`. If only this Skill is installed, ask the user to clone the accompanying GitHub project before continuing.

## Configure A New Installation

1. Inspect `README.md`, `config.example.yaml`, and the current platform.
2. Check for Python 3.10+, Node.js 18+, and an Obsidian Vault path.
3. Install dependencies with `bash scripts/bootstrap.sh` when missing. Network and browser installation may require user approval.
4. Run `.venv/bin/python -m pipeline.setup` interactively.
5. Let the user scan the Douyin login QR code in the opened browser.
6. Verify that the requested folder name is selected and that a non-empty folder ID is written to `config.yaml`.
7. Run `.venv/bin/python -m pipeline.run` once before installing or declaring the schedule healthy.

Do not guess the Vault path, folder name, or schedule when they cannot be discovered locally.

## Choose Core-Point Mode

- Use `summarize.mode: openai` for a standalone scheduled pipeline. Store the key in `secrets/runtime.env`, never in tracked configuration.
- Use `summarize.mode: manual` only when the user accepts placeholders or explicitly wants a Codex automation to fill them after each run.
- Never add a quote-summary section. Preserve only `核心观点` and `逐字稿`.

## Manage Scheduling

Use the project scheduler for local macOS/Linux cron jobs:

```bash
.venv/bin/python -m pipeline.scheduler install
.venv/bin/python -m pipeline.scheduler status
.venv/bin/python -m pipeline.scheduler uninstall
```

Update `runtime.schedule` through `pipeline.setup` or a validated five-field cron expression. Reinstall after changing it.

If the user explicitly requests a Codex recurring automation, use the Codex automation tool instead and provide absolute project and Vault paths in its prompt.

## Verify Success

Confirm all of the following:

- Collection validation selects the named folder, not recommendations.
- A newly saved item creates exactly one Markdown file.
- The file is inside the configured Vault subdirectory.
- The note contains YAML frontmatter, `核心观点`, and `逐字稿`.
- `state/processed.json` is updated only after a successful write.
- A second run reports no new items.
- `pipeline.scheduler status` shows the expected schedule when scheduling is requested.

## Troubleshoot

Read [references/operations.md](references/operations.md) for login, browser, model-download, empty-audio, and scheduler failures. Preserve failed items as unprocessed so they can retry.

## Publish Or Modify The Project

Before committing or pushing:

1. Run `python -m unittest discover -s tests -v` and `python -m compileall -q pipeline`.
2. Check `git status --ignored` for `config.yaml`, `secrets/`, `.work/`, `.models/`, `state/`, and `run.log`.
3. Scan tracked files for absolute home paths, cookies, tokens, and real Vault names.
4. Keep `package-lock.json` and dependency pins reproducible.
5. Do not include generated Obsidian notes or downloaded media.
