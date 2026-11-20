import pytest

from lemonaid.slack import api, session, signed_out, signin

from .shared import COOKIE, Keychain


def test_tokens_come_best_first_without_repeats():
    look = {
        "teams": [{"token": "xoxc-enterprise"}, {"token": ""}, {"token": "xoxc-workspace"}],
        "stored": [{"token": "xoxc-workspace"}, {"token": "xoxb-not-a-client-token"}],
        "called": "xoxc-from-a-call",
    }

    assert signin.tokens(look) == ["xoxc-enterprise", "xoxc-workspace", "xoxc-from-a-call"]


def test_the_first_token_slack_accepts_becomes_the_session(monkeypatch):
    def auth_test(current, method, **params):
        assert method == "auth.test" and current.cookie == COOKIE
        if current.token == "xoxc-enterprise":
            raise api.Expired("auth.test: invalid_auth")
        return {
            "ok": True,
            "url": "https://acme.enterprise.slack.com/",
            "user": "sam",
            "user_id": "U0SAM",
            "team": "Acme",
            "team_id": "T0ACME",
        }

    monkeypatch.setattr(api, "call", auth_test)

    found = signin.capture(
        ["xoxc-enterprise", "xoxc-workspace"], COOKIE, "2027-12-25", "https://acme.slack.com/"
    )

    assert found is not None
    assert (found.token, found.api_url, found.user) == (
        "xoxc-workspace",
        "https://acme.enterprise.slack.com/",
        "sam",
    )


def test_keeping_a_session_ends_the_pause_a_refused_one_caused(monkeypatch):
    keychain = Keychain()
    monkeypatch.setattr(session, "_run", keychain)
    monkeypatch.setattr(api, "call", lambda current, method, **params: {"ok": True, "user": "sam"})
    [old] = [signin.capture(["xoxc-old"], COOKIE, "", "https://acme.slack.com/")]
    assert old is not None
    signed_out.mark(old)
    assert signed_out.problem(old)

    new = signin.capture(["xoxc-new"], COOKIE, "", "https://acme.slack.com/")
    assert new is not None
    signin.keep(new)

    assert session.load() == new
    assert signed_out.problem(new) == ""


@pytest.mark.parametrize("look", [{}, {"teams": None, "called": ""}])
def test_a_page_with_no_token_has_no_candidates(look):
    assert signin.tokens(look) == []
