from unittest.mock import patch

import pytest

from titan_plugin_docker.clients.network.docker_network import DockerNetwork
from titan_plugin_docker.exceptions import DockerCommandError


@pytest.fixture
def network() -> DockerNetwork:
    with patch("shutil.which", return_value="/usr/bin/docker"):
        return DockerNetwork()


def test_stream_command_invokes_on_line_for_each_line(network: DockerNetwork) -> None:
    lines = []

    output = network.stream_command(["python3", "-c", "print('a'); print('b')"], on_line=lines.append)

    assert lines == ["a", "b"]
    assert output == "a\nb"


def test_stream_command_raises_on_nonzero_exit(network: DockerNetwork) -> None:
    with pytest.raises(DockerCommandError):
        network.stream_command(
            ["python3", "-c", "import sys; print('boom'); sys.exit(1)"],
            on_line=lambda line: None,
        )


def test_stream_command_check_false_does_not_raise(network: DockerNetwork) -> None:
    output = network.stream_command(
        ["python3", "-c", "import sys; print('boom'); sys.exit(1)"],
        on_line=lambda line: None,
        check=False,
    )

    assert output == "boom"


# --- Output sanitization: TUI widgets render control chars raw ---

def test_sanitize_strips_ansi_sequences():
    from titan_plugin_docker.clients.network.docker_network import _sanitize_output_line
    line = "\x1b[1m#5 [internal] load build definition\x1b[0m from Dockerfile"
    assert _sanitize_output_line(line) == "#5 [internal] load build definition from Dockerfile"


def test_sanitize_strips_cursor_movement_and_erase():
    from titan_plugin_docker.clients.network.docker_network import _sanitize_output_line
    line = "\x1b[1A\x1b[0K#6 exporting layers"
    assert _sanitize_output_line(line) == "#6 exporting layers"


def test_sanitize_carriage_return_keeps_final_state():
    from titan_plugin_docker.clients.network.docker_network import _sanitize_output_line
    assert _sanitize_output_line("Downloading  10%\rDownloading 100%") == "Downloading 100%"


def test_sanitize_plain_text_untouched():
    from titan_plugin_docker.clients.network.docker_network import _sanitize_output_line
    line = "#7 naming to docker.io/acme/reports-scheduler:1.2.3 done"
    assert _sanitize_output_line(line) == line
