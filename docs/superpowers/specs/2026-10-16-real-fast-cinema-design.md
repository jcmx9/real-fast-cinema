# real-fast-cinema – Design

Date: 2026-10-16
Status: Approved (brainstorming), pending spec review

## 1. Goal

A self-hosted service that regularly searches video services (starting with
[MediathekViewWeb](https://mediathekviewweb.de)) for films from maintained
title lists and reacts to new hits – either by notifying (mail with links) or
by downloading the film in maximum quality to a target folder with a defined
file name.

## 2. Concepts

| Concept | Description |
|---|---|
| **Source** | A searchable service (plugin). First: `mediathekviewweb`. |
| **Title list** | Separate plain-text file, one search term per line, `#` = comment, blank lines ignored. Shared between profiles. |
| **Profile** | One YAML file. Binds one or more sources, exactly one title list, filters, an action, download options, notification options and an interval. There is no default profile. |
| **Hit** | Normalized search result from any source. |
| **Action** | `info` (notify), `download`, or `both`. |
| **Notifier** | Exchangeable channel. First: e-mail via SMTP. |

## 3. Matching rules

- A search term matches a hit if **all words** of the term occur in
  `topic + " " + title` (case-insensitive, Unicode-normalized, order
  irrelevant). `Miss Marple` finds all Miss Marple films.
- Profile filters (all optional):
  - `min_duration` (e.g. `60m`)
  - `audio_description`: `true | false | any` (default `false`)
  - `sign_language`: `true | false | any` (default `false`)
  - `trailer`: `true | false | any` (default `false`)
  - `subtitles`: `true | false | any` (default `any`)
  - `language`: e.g. `de`, `ov`, `any` (default `any`)
  - `exclude`: list of words; a hit containing any of them is dropped
- Feature flags (`audio_description`, `sign_language`, `trailer`, `language`,
  `year`) are derived by the **source plugin**, because only it knows how its
  service marks them. Observed MediathekViewWeb markers: `(Audiodeskription)`,
  `(Gebärdensprache)`, `Trailer:` prefix, `(YYYY)` year, `(OV)` /
  `Originalversion`; subtitles via non-empty `url_subtitle`.

## 4. Deduplication

- **Normalized key** = `topic_norm | title_norm`:
  1. lowercase, Unicode NFKD, strip diacritics
  2. remove parenthesized markers (`(Audiodeskription)`, `(2025)`, …; year
     is extracted to `year` first)
  3. remove topic prefix (`Tatort: Unter Freunden` with topic `Tatort` →
     `unter freunden`)
  4. remove punctuation, collapse whitespace
- Two hits are the **same film** if keys are equal **and** durations differ
  by at most `max(60 s, 2 %)`.
- Within a run, hits are grouped; the **best hit** per group wins:
  direct MP4 before HLS → HD URL available → newest timestamp.
- Across runs: each film triggers **once per profile**. State lives in SQLite.
- Quality: always the maximum available (`url_video_hd` → `url_video` →
  `url_video_low`). Not configurable for now.

## 5. Configuration layout

```
config/
  config.yaml          # global settings
  profiles/*.yaml      # one profile per file
  titles/*.txt         # title lists
```

`config.yaml`:

```yaml
data_dir: /data
downloads_root: /media
smtp:
  host: smtp.example.org
  port: 587
  starttls: true
  user: rf-cinema@example.org
  from: rf-cinema@example.org
  # password from env RF_CINEMA_SMTP_PASSWORD
mail_to: [me@example.org]
defaults:
  every: 6h
  max_retries: 3
```

Profile:

```yaml
name: miss-marple
sources: [mediathekviewweb]
titles: krimis.txt
every: 6h
filters:
  min_duration: 60m
  audio_description: false
  sign_language: false
  language: de
  exclude: [Trailer]
action: download          # info | download | both
download:
  target: filme/miss-marple       # relative to downloads_root
  rename: "{topic} - {title}.{ext}"
notify: errors            # always | errors | never (download only)
mail_to: [other@example.org]      # optional override
```

All config is validated with Pydantic. Profiles and title lists are re-read
before every run (changes apply without restart).

## 6. Components

```
src/real_fast_cinema/
  __init__.py       # __version__
  __main__.py
  cli.py            # typer: run, daemon, check, list-sources, --version
  config.py         # Pydantic models: GlobalConfig, Profile, Filters, DownloadOpts
  loader.py         # load config.yaml, profiles/*.yaml, titles/*.txt
  exceptions.py
  models.py         # Hit, Report
  sources/
    base.py         # Protocol Source: name, search(term) -> list[Hit]; registry
    mediathekviewweb.py
  matching.py       # word match, filters, normalization, grouping
  store.py          # SQLite: handled hits, attempts, last run per profile
  actions/
    download.py     # httpx stream / ffmpeg HLS, .part → atomic rename
  notifiers/
    base.py         # Protocol Notifier: send(report); registry
    email.py        # SMTP, multipart text + HTML
  runner.py         # one run of one profile
  scheduler.py      # daemon loop
```

`Hit` fields: `source`, `source_id`, `channel`, `topic`, `title`,
`description`, `duration` (s), `published` (datetime), `video_url`,
`is_hls`, `page_url`, `subtitle_url`, `audio_description`, `sign_language`,
`trailer`, `language`, `year`.

## 7. Data flow (one profile run)

1. Load title list → search terms.
2. For each term × each source: `Source.search(term)`.
3. Word match against `topic + title`.
4. Apply profile filters.
5. Group within run, pick best hit per group.
6. Drop groups already handled for this profile (SQLite).
7. Execute action; record status.
8. Build report; send via notifier according to `action` / `notify`.

**MediathekViewWeb source:** `POST https://mediathekviewweb.de/api/query`
with `queries: [{fields: ["title","topic"], query: term}]`, sorted by
timestamp desc, page size 50, pagination up to a fixed cap (e.g. 500 hits per
term). The API pre-filters; our matcher re-checks exactly.

**Status semantics (per profile + key):**

| action | done when |
|---|---|
| `info` | mail sent successfully |
| `download` | download succeeded |
| `both` | both succeeded |

## 8. Download

- MP4: httpx streaming into `<target>/.<name>.part`, verify size if
  `Content-Length` is present, then atomic rename.
- HLS (`.m3u8`): `ffmpeg -i <url> -c copy <part>` via
  `subprocess.run([...], check=True)`, never `shell=True`.
- Rename placeholders: `{topic}`, `{title}` (normalized display title without
  markers), `{channel}`, `{year}`, `{date}` (supports format spec, e.g.
  `{date:%Y-%m-%d}`), `{ext}`. Invalid filename characters are replaced.
- Resolved path must lie inside the target folder (no path traversal).
  Target folder must lie inside `downloads_root`; it is created if missing.
- Existing file → never overwritten; suffix ` (2)`, ` (3)` … plus warning.
- Downloads run sequentially.

## 9. Notification

- One report per profile and run with sections `found`, `downloaded`,
  `failed`.
- Sent when `action` is `info`/`both` and there are new hits; for downloads
  according to `notify` (`always | errors | never`, default `errors`).
- E-mail: one digest mail per profile/run, multipart text + HTML; per film:
  title, topic, channel, duration, year, page link, direct video link.
- SMTP password only from env `RF_CINEMA_SMTP_PASSWORD`.

## 10. Error handling

| Error | Behavior |
|---|---|
| Source unreachable / timeout / 5xx | 3 retries with backoff; then skip this source for this run, continue with others; log + include in report |
| Download fails | delete `.part`; status `failed`, attempts+1; retry next run until `max_retries` (default 3); then final `failed`, reported once |
| Mail fails | nothing marked `notified` → retried next run |
| Invalid config / missing title list | `check` and `run` abort with clear message (no traceback); `daemon` skips the broken profile and logs an error |
| ffmpeg missing | detected at startup; HLS hits become `failed` with hint |

## 11. CLI

- `rf-cinema run [--profile NAME] [--config DIR]` – one run of all (or one)
  profiles, then exit.
- `rf-cinema daemon [--config DIR]` – loop; executes due profiles by their
  `every`; last-run times persisted in SQLite (restart does not re-trigger).
- `rf-cinema check [--profile NAME] [--config DIR]` – validate config and dry
  run: shows what would be found and done, executes nothing, writes no state.
- `rf-cinema list-sources`
- `--version` / `-V`, no args = help; verbosity `-Q` / `-v` / `-vv` per
  project conventions. Log file in `data_dir`; in container also stdout.

## 12. Deployment

- `Dockerfile`: `python:3.13-slim` + `ffmpeg`, multi-stage with uv, non-root
  user, default command `rf-cinema daemon --config /config`.
- Volumes: `/config`, `/data`, `/media`.
- `docker-compose.yml` example, `.env` (gitignored) for the SMTP password.
- `config.example/` with sample `config.yaml`, profile and title list.
- Target host: `s2` (Hetzner, Debian 13, Docker).

## 13. Testing

pytest, coverage ≥ 80 %, core modules (`matching`, `store`, `runner`) ≥ 95 %.
No network in CI.

- **matching:** parametrized cases from recorded real API responses (JSON
  fixtures, e.g. Tatort variants incl. ORF/HLS, `(2025)`, AD, DGS, trailer).
- **sources/mediathekviewweb:** mapping, pagination, retries via
  `httpx.MockTransport`; optional `@pytest.mark.live` test, deselected by
  default.
- **store:** tmp SQLite, status transitions, retry limit.
- **download:** MockTransport; `.part`/rename, collision suffix, path
  traversal; HLS with mocked `subprocess.run`.
- **notifiers/email:** mocked `smtplib`; content, recipients, failure.
- **runner:** end-to-end with fake source, fake notifier, tmp store; all
  `action` × `notify` combinations; "once per film" across two runs.
- **scheduler:** fake clock; due calculation, restart behavior.
- **cli:** `CliRunner`: `--version`, no-args help, `check`, error output.

## 14. Project conventions

Follows `~/GitHub/CLAUDE.md`: CalVer (`26.10.0.dev1` start), bump-my-version,
`scripts/release.sh`, CI workflow (ruff, mypy strict, pytest), pre-commit,
Dependabot, MIT license, author `jcmx9`, `README.md` + `README.en.md` in
parity, CHANGELOG, CONTRIBUTING, SECURITY, CODEOWNERS.

**Deviation:** `release.yml` does not publish to PyPI. It creates a GitHub
release and optionally pushes a Docker image to GHCR.

Dependencies: `typer`, `pydantic`, `httpx`, `pyyaml`. System: `ffmpeg`.

## 15. Out of scope (for now)

- Web UI / API
- Further sources and notifiers (architecture prepared via registries)
- Quality selection, fuzzy matching, parallel downloads
