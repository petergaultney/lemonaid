import json

from lemonaid.usage import samples


def test_claude_limits_round_trip_through_the_statusline_hook(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    samples.save_claude_limits(
        {"rate_limits": {"five_hour": {"used_percentage": 12, "resets_at": 5}}}
    )
    assert samples.claude_samples(samples.claude_limits_file()) == {
        "claude five_hour": samples.Sample(12, 5, 300)
    }


def test_statusline_data_without_rate_limits_saves_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    samples.save_claude_limits({"model": {}})
    assert not samples.claude_limits_file().exists()


def test_codex_takes_newest_event_across_rollouts(tmp_path):
    def rollout(name: str, ts: str, used: float) -> None:
        path = tmp_path / "2026" / "10" / "08" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        limits = {
            "primary": {"used_percent": used, "window_minutes": 10080, "resets_at": 9},
            "secondary": None,
        }
        path.write_text(json.dumps({"timestamp": ts, "payload": {"rate_limits": limits}}) + "\n")

    rollout("rollout-a.jsonl", "2026-10-08T10:00:00Z", 50)
    rollout("rollout-b.jsonl", "2026-10-08T11:00:00Z", 60)
    assert samples.codex_samples(tmp_path) == {
        "codex primary (10080min)": samples.Sample(60, 9, 10080)
    }
