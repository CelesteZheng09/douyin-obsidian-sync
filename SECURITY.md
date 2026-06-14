# Security

## Sensitive local files

Never commit:

- `config.yaml`
- `secrets/`
- `state/`
- `.work/`
- `.models/`
- Obsidian notes containing private content

The setup wizard stores optional API credentials in `secrets/runtime.env` with mode `0600`. Douyin browser state and yt-dlp cookies are also stored under `secrets/`.

## Reporting

Open a private security advisory in the GitHub repository for vulnerabilities involving credential exposure, path traversal, command injection, or unintended collection access. Do not include live cookies, API keys, or private transcripts in reports.
