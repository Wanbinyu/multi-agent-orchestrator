"""Release version sources must stay aligned."""
from pathlib import Path
import tomllib

from src.version import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_beta7_version_sources_and_release_notes_are_aligned():
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project_version = tomllib.load(stream)["project"]["version"]

    assert __version__ == "0.1.0b7"
    assert project_version == __version__
    assert (ROOT / "docs" / "RELEASE_NOTES_v0.1.0-beta.7.md").is_file()
    assert (ROOT / "docs" / "RELEASE_NOTES_v0.1.0-beta.6.md").is_file()
