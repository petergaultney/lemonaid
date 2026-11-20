from lemonaid import slack_config


def test_the_slack_table_reads_its_settings():
    found = slack_config.parse(
        {
            "workspace": "https://acme.slack.com/",
            "push": False,
            "fetch_every": 30,
            "presence_every": 0,
        }
    )

    assert found == slack_config.SlackConfig("https://acme.slack.com/", False, 30.0, 0.0)


def test_bad_values_keep_their_defaults_with_a_warning(capsys):
    found = slack_config.parse(
        {"workspace": "acme.slack.com", "push": "yes", "fetch_every": 1, "presence_every": -5}
    )

    assert found == slack_config.SlackConfig()
    assert capsys.readouterr().err.count("Warning: [slack]") == 4
