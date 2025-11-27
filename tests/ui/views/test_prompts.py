# tests/ui/views/test_prompts.py
import pytest
from unittest.mock import MagicMock
from rich.prompt import Prompt, Confirm, IntPrompt
from titan_cli.ui.views.prompts import PromptsRenderer
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.messages import msg

@pytest.fixture
def mock_text_renderer(mocker):
    """Fixture to create a mock TextRenderer."""
    mock = mocker.MagicMock(spec=TextRenderer)
    # The console is retrieved from the text_renderer, so mock it too
    mock.console = mocker.MagicMock()
    return mock

def test_ask_int_success(mocker, mock_text_renderer):
    """Test that ask_int returns a valid integer on the first try."""
    # Patch the underlying rich prompt
    mocker.patch.object(IntPrompt, "ask", return_value=10)
    
    prompts = PromptsRenderer(text_renderer=mock_text_renderer)
    result = prompts.ask_int("Enter a number", min_value=5, max_value=15)
    
    assert result == 10
    mock_text_renderer.error.assert_not_called() # No error messages should be shown

def test_ask_int_handles_none_and_reprompts(mocker, mock_text_renderer):
    """Test the fix for the TypeError when a user just hits Enter."""
    # Simulate user hitting Enter (returns None), then entering a valid number
    mocker.patch.object(IntPrompt, "ask", side_effect=[None, 5])
    
    prompts = PromptsRenderer(text_renderer=mock_text_renderer)
    result = prompts.ask_int("Enter a number")
    
    assert result == 5
    # Assert that the "missing value" error was called once
    mock_text_renderer.error.assert_called_once_with(msg.Prompts.MISSING_VALUE, show_emoji=False)

def test_ask_int_handles_value_too_low(mocker, mock_text_renderer):
    """Test that ask_int re-prompts when the value is below min_value."""
    # Simulate user entering 2 (too low), then a valid 10
    mocker.patch.object(IntPrompt, "ask", side_effect=[2, 10])
    
    prompts = PromptsRenderer(text_renderer=mock_text_renderer)
    result = prompts.ask_int("Enter a number", min_value=5)
    
    assert result == 10
    # Assert that the "value too low" error was called once
    mock_text_renderer.error.assert_called_once_with(msg.Prompts.VALUE_TOO_LOW.format(min=5), show_emoji=False)

def test_ask_int_handles_value_too_high(mocker, mock_text_renderer):
    """Test that ask_int re-prompts when the value is above max_value."""
    # Simulate user entering 20 (too high), then a valid 10
    mocker.patch.object(IntPrompt, "ask", side_effect=[20, 10])
    
    prompts = PromptsRenderer(text_renderer=mock_text_renderer)
    result = prompts.ask_int("Enter a number", max_value=15)
    
    assert result == 10
    # Assert that the "value too high" error was called once
    mock_text_renderer.error.assert_called_once_with(msg.Prompts.VALUE_TOO_HIGH.format(max=15), show_emoji=False)

def test_ask_text_with_validator(mocker, mock_text_renderer):
    """Test that ask_text uses the provided validator and re-prompts on failure."""
    # Simulate user entering "bad", then "good"
    mocker.patch.object(Prompt, "ask", side_effect=["bad", "good"])
    
    # A simple validator that only accepts "good"
    def my_validator(value: str) -> bool:
        return value == "good"
        
    prompts = PromptsRenderer(text_renderer=mock_text_renderer)
    result = prompts.ask_text("Enter 'good'", validator=my_validator)
    
    assert result == "good"
    # Assert that the "invalid input" error was called once
    mock_text_renderer.error.assert_called_once_with(msg.Prompts.INVALID_INPUT, show_emoji=False)

def test_ask_confirm_returns_true(mocker, mock_text_renderer):
    """Test that ask_confirm returns True when user confirms."""
    mocker.patch.object(Confirm, "ask", return_value=True)
    
    prompts = PromptsRenderer(text_renderer=mock_text_renderer)
    result = prompts.ask_confirm("Continue?")
    
    assert result is True

def test_ask_confirm_returns_false(mocker, mock_text_renderer):
    """Test that ask_confirm returns False when user denies."""
    mocker.patch.object(Confirm, "ask", return_value=False)
    
    prompts = PromptsRenderer(text_renderer=mock_text_renderer)
    result = prompts.ask_confirm("Continue?")
    
    assert result is False

def test_ask_choice_returns_selection(mocker, mock_text_renderer):
    """Test that ask_choice returns the selected choice."""
    mocker.patch.object(Prompt, "ask", return_value="blue")
    
    prompts = PromptsRenderer(text_renderer=mock_text_renderer)
    result = prompts.ask_choice("Choose a color", choices=["red", "green", "blue"])
    
    assert result == "blue"

def test_ask_menu_returns_selection(mocker, mock_text_renderer):
    """Test that ask_menu returns the correct value for a selection."""
    # Simulate user choosing option '2'
    mocker.patch.object(Prompt, "ask", return_value="2")
    
    options = [
        ("Option 1", "one"),
        ("Option 2", "two"),
    ]
    
    prompts = PromptsRenderer(text_renderer=mock_text_renderer)
    result = prompts.ask_menu("Select an option", options=options)
    
    assert result == "two"
    mock_text_renderer.error.assert_not_called()

def test_ask_menu_handles_invalid_input(mocker, mock_text_renderer):
    """Test that ask_menu re-prompts after invalid (non-integer) input."""
    # Simulate user entering "a", then a valid "1"
    mocker.patch.object(Prompt, "ask", side_effect=["a", "1"])
    
    options = [("Option 1", "one")]
    
    prompts = PromptsRenderer(text_renderer=mock_text_renderer)
    result = prompts.ask_menu("Select an option", options=options)
    
    assert result == "one"
    mock_text_renderer.error.assert_called_once_with(msg.Prompts.NOT_A_NUMBER, show_emoji=False)