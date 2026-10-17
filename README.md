# real-fast-cinema

> Durchsucht Mediatheken regelmäßig nach Filmen aus deinen Titellisten und meldet oder lädt sie herunter.

**Version:** 26.10.0.dev1 · **Sprache:** Deutsch | [English](README.en.md)

[![CI](https://github.com/jcmx9/real-fast-cinema/actions/workflows/ci.yml/badge.svg)](https://github.com/jcmx9/real-fast-cinema/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jcmx9/real-fast-cinema/branch/main/graph/badge.svg)](https://codecov.io/gh/jcmx9/real-fast-cinema)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Beschreibung

`rf-cinema` arbeitet **Profile** ab. Ein Profil verbindet einen oder mehrere **Dienste**
(zunächst [MediathekViewWeb](https://mediathekviewweb.de)) mit einer **Titelliste**
(eigene Textdatei), **Filtern** und einer **Aktion**:

- `info`: Sammelmail mit Links zu allen neuen Treffern
- `download`: Download in höchster Qualität in einen Zielordner mit Namensschema
- `both`: beides

Ein Suchbegriff trifft, wenn **alle Wörter** in Thema und Titel vorkommen
(`Miss Marple` findet alle Miss-Marple-Filme). Jeder Film löst pro Profil nur
**einmal** aus, auch wenn er auf mehreren Sendern läuft.

## Voraussetzungen

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)
- Git
- ffmpeg (für HLS-Streams, im Docker-Image enthalten)

## Installation

```bash
uv tool install git+https://github.com/jcmx9/real-fast-cinema.git
```

Oder als Container:

```bash
cp -r config.example config && cp .env.example .env   # anpassen
mkdir -p data media && sudo chown 1000:1000 data media
docker compose up -d
```

Das Image wird bis zum ersten Release lokal gebaut (`pull_policy: build` in `docker-compose.yml`).

## Update

```bash
uv tool install --force git+https://github.com/jcmx9/real-fast-cinema.git
```

Container: `docker compose pull && docker compose up -d`

## Verwendung

```bash
rf-cinema check  -c config          # Konfiguration prüfen + Probelauf
rf-cinema run    -c config          # alle Profile einmal ausführen
rf-cinema run    -c config -p krimis-info
rf-cinema daemon -c config          # dauerhaft, Profile nach Intervall
rf-cinema list-sources
rf-cinema --help
rf-cinema --version
```

## Konfiguration

```
config/
  config.yaml          # global: Pfade, SMTP, Empfänger, Defaults
  profiles/*.yaml      # ein Profil pro Datei
  titles/*.txt         # Titellisten: ein Suchbegriff pro Zeile, # = Kommentar
```

Profil-Beispiel:

```yaml
name: miss-marple-download
sources: [mediathekviewweb]
titles: krimis.txt
every: 6h
filters:
  min_duration: 60m        # Trailer/Clips raus
  audio_description: false # true | false | any
  sign_language: false
  trailer: false
  subtitles: any
  language: any            # de | ov | any
  exclude: [Hörfassung]
action: download           # info | download | both
download:
  target: filme/krimis     # relativ zu downloads_root
  rename: "{topic} - {title} ({year}).{ext}"
notify: errors             # always | errors | never
```

Platzhalter für `rename`: `{topic}`, `{title}`, `{channel}`, `{year}` (Jahr aus dem Titel,
sonst Sendejahr), `{date}` (z. B. `{date:%Y-%m-%d}`), `{ext}`. Das SMTP-Passwort kommt
aus der Umgebungsvariablen `RF_CINEMA_SMTP_PASSWORD`. Profile und Titellisten werden
vor jedem Lauf neu eingelesen.

## Optionen

| Option | Beschreibung |
|--------|-------------|
| `--version`, `-V` | Version anzeigen und beenden |
| `--help` | Hilfe anzeigen und beenden |
| `--config`, `-c` | Konfigurationsverzeichnis (Standard `config`, Env `RF_CINEMA_CONFIG`) |
| `--profile`, `-p` | Nur dieses Profil (`run`, `check`) |
| `--silent`, `-Q` | Keine Konsolenausgabe, nur Log-Datei |
| `--verbose`, `-v` | Erweiterte Ausgabe |
| `--debug`, `-vv` | Debug-Ausgabe |

Exit-Codes von `run`: `0` ok, `1` Fehler, `2` Teilfehler (Download oder Dienst fehlgeschlagen).

## Entwicklung

```bash
git clone git@github.com:jcmx9/real-fast-cinema.git
cd real-fast-cinema
uv sync
uv run pytest
uv run pytest -m live --no-cov # Tests gegen die echte API
uv run ruff check --fix . && uv run ruff format .
uv run mypy src/
```

## Projektstruktur

```
src/real_fast_cinema/  – Quellcode
tests/                 – Tests (pytest)
config.example/        – Beispielkonfiguration
scripts/               – Release-Skript
docs/                  – Dokumentation
.github/workflows/     – CI/CD-Pipelines
```

## Versionierung

Dieses Projekt nutzt [CalVer](https://calver.org/) im Format `YY.M.MICRO`.
Releases werden mit [bump-my-version](https://github.com/callowayproject/bump-my-version)
verwaltet, siehe [docs/github-release.md](docs/github-release.md).

## Mitwirken

Den vollständigen Ablauf beschreibt [CONTRIBUTING.md](CONTRIBUTING.md). Kurzfassung:

1. Repository forken
2. Feature-Branch von `dev` anlegen (`git checkout -b feature/my-feature dev`)
3. Änderungen committen (Conventional Commits)
4. Pushen und PR gegen `dev` erstellen

## Sicherheit

Sicherheitslücken bitte **nicht** über öffentliche Issues melden.
Den Ablauf beschreibt [SECURITY.md](SECURITY.md).

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md).

## Lizenz

MIT – siehe [LICENSE](LICENSE).
