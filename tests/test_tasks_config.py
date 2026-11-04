from lemonaid import tasks_config


def test_inspector_settings_parse_and_bad_values_fall_back(capsys):
    good = tasks_config.parse(
        {
            "checker": ["my-checker", "--strict"],
            "checker_timeout": 5,
            "inspect_interval": 600,
            "challenge_interval": 0,
            "opt_out": {"Design.sketch": " a human drives it "},
            "policy": {"idle_grace": 300, "adjudicator": "human:sam"},
        }
    )
    bad = tasks_config.parse(
        {
            "checker": "my-checker",
            "checker_timeout": 0,
            "inspect_interval": "often",
            "challenge_interval": -1,
            "opt_out": {"Design.sketch": ""},
            "policy": {"x": True},
        }
    )

    assert good.checker == ("my-checker", "--strict")
    assert (good.checker_timeout, good.challenge_interval) == (5.0, 0.0)
    assert (good.inspect_interval, bad.inspect_interval) == (600.0, 0.0)
    assert good.opt_out == {"Design.sketch": "a human drives it"}
    assert good.policy == {"idle_grace": "300", "adjudicator": "human:sam"}
    assert (bad.checker, bad.checker_timeout, bad.policy) == ((), 30.0, {})
    assert (bad.challenge_interval, bad.opt_out) == (300.0, {})
    assert capsys.readouterr().err.count("Warning") == 6
