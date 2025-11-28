# tests/ui/components/test_typography.py
import pytest
from unittest.mock import MagicMock
from titan_cli.ui.components.typography import TextRenderer

@pytest.fixture
def mock_console():
    """Fixture for a mocked Rich Console."""
    return MagicMock()

def test_title(mock_console):
    """Test that title prints with correct style."""
    text_renderer = TextRenderer(console=mock_console)
    text_renderer.title("Hello")
    mock_console.print.assert_called_once_with("[bold primary]Hello[/bold primary]", justify="left")

def test_body(mock_console):
    """Test that body prints with correct style."""
    text_renderer = TextRenderer(console=mock_console)
    text_renderer.body("Hello")
    mock_console.print.assert_called_once_with("Hello")

def test_styled_text_multiple_parts(mock_console):
    """Test styled_text with multiple styled parts"""
    text = TextRenderer(console=mock_console)

    text.styled_text(
        ("  1. ", "primary"),
        ("Label", "bold"),
        (" - ", "dim"),
        ("description", "dim")
    )

    # Verify Text.assemble was used correctly
    assert mock_console.print.called
    call_args = mock_console.print.call_args

    # First argument should be a Text object
    from rich.text import Text
    assert isinstance(call_args[0][0], Text)


def test_styled_text_with_justify(mock_console):
    """Test styled_text with justify parameter"""
    text = TextRenderer(console=mock_console)

    text.styled_text(
        ("Title", "bold"),
        (" - ", "dim"),
        ("Subtitle", "italic"),
        justify="center"
    )

    # Verify justify was passed
    assert mock_console.print.call_args[1]["justify"] == "center"
