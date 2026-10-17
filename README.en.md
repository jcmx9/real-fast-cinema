# real-fast-cinema

> Regularly searches media libraries for films from your title lists and notifies you or downloads them.

**Version:** 26.10.0.dev1 · **Language:** [Deutsch](README.md) | English

[![CI](https://github.com/jcmx9/real-fast-cinema/actions/workflows/ci.yml/badge.svg)](https://github.com/jcmx9/real-fast-cinema/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jcmx9/real-fast-cinema/branch/main/graph/badge.svg)](https://codecov.io/gh/jcmx9/real-fast-cinema)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Description

`rf-cinema` processes **profiles**. A profile combines one or more **sources**
(initially [MediathekViewWeb](https://mediathekviewweb.de)) with a **title list**
(separate text file), **filters** and an **action**:

- `info`: digest mail with links to all new hits
- `download`: download in maximum quality into a target folder with a naming scheme
- `both`: both

A search term matches if **all words** occur in topic and title
(`Miss Marple` finds all Miss Marple films). Each film triggers only **once**
per profile, even if it is offered by several channels.

## Prerequisites

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)
- Git
- ffmpeg (for HLS streams, included in the Docker image)

## Installation

```bash
uv tool install git+https://github.com/jcmx9/real-fast-cinema.git
```

Or as a container:

```bash
cp -r config.example config && cp .env.example .env   # adjust
docker compose up -d
```

## Update

```bash
uv tool install --force git+https://github.com/jcmx9/real-fast-cinema.git
```

Container: `docker compose pull && docker compose up -d`

## Usage

```bash
rf-cinema check  -c config          # validate configuration + dry run
rf-cinema run    -c config          # run all profiles once
rf-cinema run    -c config -p krimis-info
rf-cinema daemon -c config          # run continuously, profiles by interval
rf-cinema list-sources
rf-cinema --help
rf-cinema --version
```

## Configuration

```
config/
  config.yaml          # global: paths, SMTP, recipients, defaults
  profiles/*.yaml      # one profile per file
  titles/*.txt         # title lists: one search term per line, # = comment
```

Profile example:

```yaml
name: miss-marple-download
sources: [mediathekviewweb]
titles: krimis.txt
every: 6h
filters:
  min_duration: 60m        # drop trailers/clips
  audio_description: false # true | false | any
  sign_language: false
  trailer: false
  subtitles: any
  language: any            # de | ov | any
  exclude: [Hörfassung]
action: download           # info | download | both
download:
  target: filme/krimis     # relative to downloads_root
  rename: "{topic} - {title} ({year}).{ext}"
notify: errors             # always | errors | never
```

Placeholders for `rename`: `{topic}`, `{title}`, `{channel}`, `{year}` (year from the
title, otherwise broadcast year), `{date}` (e.g. `{date:%Y-%m-%d}`), `{ext}`. The SMTP
password is read from the environment variable `RF_CINEMA_SMTP_PASSWORD`. Profiles and
title lists are re-read before every run.

## Options

| Option | Description |
|--------|------------|
| `--version`, `-V` | Show version and exit |
| `--help` | Show help text and exit |
| `--config`, `-c` | Configuration directory (default `config`, env `RF_CINEMA_CONFIG`) |
| `--profile`, `-p` | Only this profile (`run`, `check`) |
| `--silent`, `-Q` | No console output, log file only |
| `--verbose`, `-v` | Extended output |
| `--debug`, `-vv` | Debug output |

Exit codes of `run`: `0` ok, `1` error, `2` partial failure (download or source failed).

## Development

```bash
git clone git@github.com:jcmx9/real-fast-cinema.git
cd real-fast-cinema
uv sync
uv run pytest
uv run pytest -m live          # tests against the real API
uv run ruff check --fix . && uv run ruff format .
uv run mypy src/
```

## Project Structure

```
src/real_fast_cinema/  – Source code
tests/                 – Tests (pytest)
config.example/        – Example configuration
scripts/               – Release script
docs/                  – Documentation
.github/workflows/     – CI/CD pipelines
```

## Versioning

This project uses [CalVer](https://calver.org/) in the format `YY.M.MICRO`.
Releases are managed with [bump-my-version](https://github.com/callowayproject/bump-my-version),
see [docs/github-release.md](docs/github-release.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow. Quick start:

1. Fork the repository
2. Create a feature branch from `dev` (`git checkout -b feature/my-feature dev`)
3. Commit changes (Conventional Commits)
4. Push and create a PR targeting `dev`

## Security

Please do **not** report security vulnerabilities via public issues.
See [SECURITY.md](SECURITY.md) for the reporting process.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT – see [LICENSE](LICENSE).
