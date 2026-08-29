import io
import json
import os
import threading

from titan_cli.external_cli.interactive_session import run_interactive_session


def test_interactive_session_bridges_input_and_output_through_a_pty():
    read_fd, write_fd = os.pipe()
    input_stream = os.fdopen(read_fd, "r")
    writer = os.fdopen(write_fd, "w")
    writer.write(json.dumps({"type": "input", "value": "hello"}) + "\n")
    writer.write(json.dumps({"type": "close"}) + "\n")
    writer.close()
    output_stream = io.StringIO()

    thread = threading.Thread(
        target=run_interactive_session,
        kwargs={
            "cli_id": "/bin/cat",
            "input_stream": input_stream,
            "output_stream": output_stream,
        },
    )
    thread.start()
    thread.join(timeout=5)
    input_stream.close()

    assert not thread.is_alive()
    events = [json.loads(line) for line in output_stream.getvalue().splitlines()]
    assert events[0] == {"type": "session_started", "cli_id": "/bin/cat"}
    assert any(event["type"] == "output" and "hello" in event["content"] for event in events)
    assert events[-1] == {"type": "session_exited", "exit_code": 0}
