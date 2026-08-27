from titan_plugin_slack.models import UISlackChannel, UISlackUser
from titan_plugin_slack.operations.target_resolution_operations import (
    build_channel_target,
    build_user_target,
    filter_channels_for_query,
    filter_users_for_query,
    normalize_search_query,
)


def test_normalize_search_query_collapses_case_and_spaces() -> None:
    assert normalize_search_query("  Alex   Smith  ") == "alex smith"


def test_filter_users_for_query_prioritizes_exact_then_prefix() -> None:
    users = [
        UISlackUser(id="U1", name="alex", real_name="Alex"),
        UISlackUser(id="U2", name="alex-team", real_name="Alex Team"),
        UISlackUser(id="U3", name="sam", real_name="Samantha Alex"),
    ]

    matches = filter_users_for_query(users, "alex")

    assert [user.id for user in matches] == ["U1", "U2", "U3"]


def test_filter_users_for_query_matches_without_accents() -> None:
    users = [
        UISlackUser(id="U1", name="gabriel", real_name="Gabriel Garcia Lopez"),
        UISlackUser(id="U2", name="gabriel-2", real_name="Gabriel García López"),
    ]

    matches = filter_users_for_query(users, "garcia")

    assert [user.id for user in matches] == ["U1", "U2"]


def test_filter_channels_for_query_strips_hash_and_limits_results() -> None:
    channels = [
        UISlackChannel(id="C1", name="engineering"),
        UISlackChannel(id="C2", name="eng-backend"),
        UISlackChannel(id="C3", name="random"),
    ]

    matches = filter_channels_for_query(channels, "#eng", limit=2)

    assert [channel.id for channel in matches] == ["C2", "C1"]


def test_build_user_target_uses_real_name_when_available() -> None:
    user = UISlackUser(id="U1", name="alex", real_name="Alex Smith")

    target = build_user_target(user, team_id="T1", connection_id="default")

    assert target.target_type == "user"
    assert target.target_id == "U1"
    assert target.target_name == "Alex Smith"
    assert target.team_id == "T1"
    assert target.connection_id == "default"


def test_build_channel_target_preserves_channel_name() -> None:
    channel = UISlackChannel(id="C1", name="engineering")

    target = build_channel_target(channel, team_id="T1")

    assert target.target_type == "channel"
    assert target.target_id == "C1"
    assert target.target_name == "engineering"
    assert target.team_id == "T1"
