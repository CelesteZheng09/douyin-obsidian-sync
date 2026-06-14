# Architecture

```text
saved browser session
        |
        v
Douyin favorite folder API -> incremental state -> extractor
                                               |-> video: yt-dlp -> PyAV -> faster-whisper
                                               |-> note: detail API -> rendered-page fallback
                                               v
                                      core-point generator
                                               v
                                      Obsidian Markdown writer
```

## Modules

- `pipeline.collector`: opens the private favorite folder with Playwright storage state and returns canonical content URLs.
- `pipeline.state`: stores successfully processed content IDs in `state/processed.json`.
- `pipeline.extractor`: downloads videos, decodes 16 kHz mono audio with PyAV, transcribes with faster-whisper, and extracts note text.
- `pipeline.writer`: creates YAML frontmatter and the two required content sections.
- `pipeline.run`: isolates failures per item and marks state only after a note is written.
- `pipeline.setup`: interactive configuration and first-run validation.
- `pipeline.scheduler`: idempotent user-crontab management.

## Trust boundaries

- Browser storage state and converted cookies are secrets.
- The Obsidian Vault is an external write target; `notes_subdir` is checked to remain inside the configured Vault.
- LLM summarization receives transcript text when `summarize.mode` is `openai`.
- Video and model downloads are local caches and should not be committed.
