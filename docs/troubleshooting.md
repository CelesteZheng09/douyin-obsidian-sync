# Troubleshooting

## Login expired

Run:

```bash
python -m pipeline.collector --login
```

## Favorite folder cannot be found

- Confirm the folder name matches exactly, including letter case.
- Run `python -m pipeline.collector --headful` and verify the correct folder opens.
- Clear `favorite_folder_id` and rerun `python -m pipeline.setup` to discover it again.

## Chrome or Chromium cannot start

```bash
npm install
npm run install-browser
```

The browser bridge first tries installed Google Chrome, then Playwright Chromium.

## Whisper model download is slow

The project disables the Xet transport and downloads serially with a longer timeout. Partial downloads resume automatically. Models are cached under `.models/`.

## Scheduled run cannot find the API Key

Use `python -m pipeline.setup` to save the key to `secrets/runtime.env`, or create it manually:

```text
OPENAI_API_KEY=your-key
```

Restrict permissions with `chmod 600 secrets/runtime.env`.

## A failed item keeps retrying

This is expected: failed items are intentionally not marked processed. Fix the reported cause in `run.log` and rerun.
