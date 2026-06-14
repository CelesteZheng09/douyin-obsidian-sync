# Operations Reference

## Login

Run `.venv/bin/python -m pipeline.collector --login`. A browser opens for QR login and saves Playwright storage state under `secrets/`.

If collection later returns a login screen, refresh the login state and rerun. Do not mark affected items processed.

## Folder Validation

The folder name must match exactly. Leave `favorite_folder_id` empty during first setup; the collector clicks the named folder, observes the target collection API response, and records its stable ID.

When Douyin changes its UI, inspect `scripts/douyin_browser.mjs`. Prefer text labels and API response validation over brittle generated CSS classes.

## Browser Runtime

Run `npm install` and `npm run install-browser`. The bridge tries system Google Chrome first, then Playwright Chromium.

## Video And ASR

`yt-dlp` reuses the saved Douyin cookies. PyAV decodes audio to 16 kHz mono WAV. Faster-whisper caches models under `.models/`, disables Xet by default, downloads serially, and uses a longer timeout.

An empty transcript can be legitimate for a silent or music-only video. Do not invent spoken content. Mark the note clearly or add a separate OCR/vision extension.

## Notes

Article items use full article Markdown from the detail API. Standard notes use the detail description before any rendered-page fallback, avoiding navigation and comment text.

One content ID should correspond to one note. Investigate and remove stale duplicates before declaring success.

## Scheduler

The scheduler manages one idempotent crontab line identified by a project-specific marker. It uses absolute paths and writes output to `run.log`.

Cron does not inherit interactive shell variables. Use `secrets/runtime.env` for `OPENAI_API_KEY` or configure an equivalent secure environment source.

## Security

- Cookie files and API keys must be mode `0600` where supported.
- Never print cookie values or API keys.
- Keep the Obsidian destination inside the configured Vault.
- Validate cron expressions before constructing commands.
- Do not publish `config.yaml`, private transcripts, state, or cache directories.
