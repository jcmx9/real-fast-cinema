"""Shared pytest fixtures."""

from pathlib import Path
from textwrap import dedent

import pytest


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "config"
    (directory / "profiles").mkdir(parents=True)
    (directory / "titles").mkdir()
    (directory / "config.yaml").write_text(
        dedent(
            f"""\
            data_dir: {tmp_path / "data"}
            downloads_root: {tmp_path / "media"}
            smtp:
              host: smtp.example.org
              port: 587
              user: bot@example.org
              from: bot@example.org
            mail_to: [me@example.org]
            """
        ),
        encoding="utf-8",
    )
    (directory / "titles" / "krimis.txt").write_text(
        "# Krimis\nMiss Marple\n\nTatort Unter Freunden\nMiss Marple\n",
        encoding="utf-8",
    )
    (directory / "profiles" / "krimis.yaml").write_text(
        dedent(
            """\
            name: krimis
            sources: [mediathekviewweb]
            titles: krimis.txt
            action: info
            """
        ),
        encoding="utf-8",
    )
    return directory
