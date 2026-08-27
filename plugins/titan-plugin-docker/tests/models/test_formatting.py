from titan_plugin_docker.models.formatting import parse_reclaimed_space


def test_parse_reclaimed_space_extracts_value() -> None:
    output = "Deleted Containers:\nabc123\n\nTotal reclaimed space: 89.45MB"

    assert parse_reclaimed_space(output) == "89.45MB"


def test_parse_reclaimed_space_case_insensitive() -> None:
    output = "total reclaimed space: 1.2GB"

    assert parse_reclaimed_space(output) == "1.2GB"


def test_parse_reclaimed_space_defaults_to_zero_when_missing() -> None:
    assert parse_reclaimed_space("Nothing to prune") == "0B"


def test_parse_reclaimed_space_handles_empty_output() -> None:
    assert parse_reclaimed_space("") == "0B"
