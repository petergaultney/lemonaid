from lemonaid.codex import limits
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


class _Codex:
    def ask(self, calls, timeout):
        assert [method for method, _ in calls] == ["account/rateLimits/read"]
        window = {"usedPercent": 60, "windowDurationMins": 10080, "resetsAt": 9}
        return [{"result": {"rateLimits": {"primary": window, "secondary": None}}}]


def test_codex_reports_its_own_limit_windows(monkeypatch):
    monkeypatch.setattr(
        limits.app_server, "once", lambda question, about, unanswered, timeout: question(_Codex())
    )

    assert samples.codex_samples(limits.windows()) == {
        "codex primary (10080min)": samples.Sample(60, 9, 10080)
    }
