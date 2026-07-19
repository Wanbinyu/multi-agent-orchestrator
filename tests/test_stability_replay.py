"""B4.S6 offline smart-mining release-gate replay."""
from __future__ import annotations

from pathlib import Path
import re
import shutil

import yaml

from src.core.engineering import StabilityReplayRunner


FIXTURE = Path(__file__).parent / "fixtures" / "smart_mining"
PUBLIC_TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
}


def test_public_fixture_contains_no_credentials_or_private_absolute_paths():
    public_text_files = [
        path
        for path in FIXTURE.rglob("*")
        if path.is_file() and path.suffix.lower() in PUBLIC_TEXT_SUFFIXES
    ]
    assert public_text_files
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in public_text_files
    )

    assert not re.search(r"(?i)(?:api[_-]?key|secret|token)\s*[:=]\s*[^\s]+", text)
    assert not re.search(r"(?i)[a-z]:[\\/]users[\\/]", text)
    assert "G:\\" not in text
    assert "{{PROJECT_ROOT}}" in text


def test_good_smart_mining_replay_passes_every_stage_without_provider(tmp_path):
    outcome = StabilityReplayRunner(FIXTURE, tmp_path / "good").run("good")

    assert outcome.passed is True, outcome.issues
    assert outcome.status == "completed"
    assert all(outcome.stages.values())
    assert {
        "targeted": True,
        "integration": True,
        "full": True,
        "smoke": True,
    }.items() <= outcome.verification.items()
    assert outcome.report_metrics["effective_deliveries"] == 1
    assert outcome.report_metrics["first_pass_runnable_rate"] == 1.0
    assert outcome.report_metrics["input_tokens"] == 0
    assert outcome.provider_calls == 0


def test_broken_mock_replay_is_blocked_by_real_browser_smoke(tmp_path):
    outcome = StabilityReplayRunner(FIXTURE, tmp_path / "broken").run(
        "broken_mock"
    )

    assert outcome.passed is False
    assert outcome.status == "blocked"
    assert outcome.stages["browser_smoke"] is False
    assert outcome.stages["completion_audit"] is False
    assert outcome.verification["smoke"] is False
    assert outcome.provider_calls == 0


def test_missing_route_replay_is_blocked_by_closure_and_commands(tmp_path):
    outcome = StabilityReplayRunner(FIXTURE, tmp_path / "missing").run(
        "missing_route"
    )

    assert outcome.passed is False
    assert outcome.status == "blocked"
    assert outcome.stages["closure"] is False
    assert outcome.stages["commands"] is False
    assert any("timeline.js" in issue for issue in outcome.issues)
    assert outcome.provider_calls == 0


def test_replay_status_stays_blocked_when_classification_contract_fails(tmp_path):
    fixture = tmp_path / "fixture"
    shutil.copytree(FIXTURE, fixture)
    transcript_path = fixture / "transcript.yaml"
    transcript = yaml.safe_load(transcript_path.read_text(encoding="utf-8"))
    transcript["expected_intent"]["kind"] = "diagnosis"
    transcript_path.write_text(
        yaml.safe_dump(transcript, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    outcome = StabilityReplayRunner(fixture, tmp_path / "workspace").run("good")

    assert outcome.stages["classification"] is False
    assert outcome.status == "blocked"
    assert outcome.report_metrics["effective_deliveries"] == 0
