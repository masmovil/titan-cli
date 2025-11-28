# tests/test_cli.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# The function to test
from titan_cli.cli import show_interactive_menu

@pytest.fixture
def mock_dependencies():
    """Fixture to mock all external dependencies of show_interactive_menu."""
    with patch('titan_cli.cli.get_version', return_value="0.1.0") as mock_version, \
         patch('titan_cli.cli.render_titan_banner') as mock_banner, \
         patch('titan_cli.cli.TitanConfig') as mock_titan_config, \
         patch('titan_cli.cli.PromptsRenderer') as mock_prompts, \
         patch('titan_cli.cli.list_projects') as mock_list_projects, \
         patch('titan_cli.cli.discover_projects') as mock_discover, \
         patch('titan_cli.cli.initialize_project') as mock_init_project, \
         patch('pathlib.Path.is_dir', return_value=True) as mock_is_dir:

        # Configure mock instances
        mock_config_instance = MagicMock()
        mock_config_instance.get_project_root.return_value = "/fake/projects"
        mock_titan_config.return_value = mock_config_instance

        mock_prompts_instance = MagicMock()
        mock_prompts.return_value = mock_prompts_instance
        
        yield {
            "version": mock_version,
            "banner": mock_banner,
            "config_class": mock_titan_config,
            "config_instance": mock_config_instance,
            "prompts_instance": mock_prompts_instance,
            "list_projects": mock_list_projects,
            "discover": mock_discover,
            "init_project": mock_init_project,
            "is_dir": mock_is_dir
        }

def test_show_interactive_menu_configure_flow(mock_dependencies):
    """
    Test the full 'Configure a New Project' flow and then exiting.
    """
    prompts_mock = mock_dependencies["prompts_instance"]
    discover_mock = mock_dependencies["discover"]
    init_project_mock = mock_dependencies["init_project"]

    # --- Simulation Setup ---
    main_menu_choice = MagicMock(action="configure")
    unconfigured_path = Path("/fake/projects/new-project")
    discover_mock.return_value = ([], [unconfigured_path])
    project_menu_choice = MagicMock(action=str(unconfigured_path.resolve()))
    exit_choice = MagicMock(action="exit")
    
    # Sequence of user choices: Configure -> Select Project -> Exit
    prompts_mock.ask_menu.side_effect = [main_menu_choice, project_menu_choice, exit_choice]
    prompts_mock.ask_text.return_value = "" # For the "Press Enter" pause

    # --- Run the function ---
    show_interactive_menu()

    # --- Assertions ---
    discover_mock.assert_called_once_with("/fake/projects")
    assert prompts_mock.ask_menu.call_count == 3 # Main menu, project menu, main menu again to exit
    init_project_mock.assert_called_once_with(unconfigured_path.resolve())
    # Check that the pause prompt was called
    prompts_mock.ask_text.assert_called_with("Press Enter to return to the main menu", default="")


def test_show_interactive_menu_list_flow(mock_dependencies):
    """
    Test the 'List Configured Projects' flow and then exiting.
    """
    prompts_mock = mock_dependencies["prompts_instance"]
    list_projects_mock = mock_dependencies["list_projects"]

    # Sequence of choices: List -> Exit
    list_choice = MagicMock(action="list")
    exit_choice = MagicMock(action="exit")
    prompts_mock.ask_menu.side_effect = [list_choice, exit_choice]
    prompts_mock.ask_text.return_value = "" # For the "Press Enter" pause

    # --- Run the function ---
    show_interactive_menu()

    # --- Assertions ---
    list_projects_mock.assert_called_once()
    assert prompts_mock.ask_menu.call_count == 2
    # Check that the pause prompt was called
    prompts_mock.ask_text.assert_called_once_with("Press Enter to return to the main menu", default="")

def test_show_interactive_menu_no_unconfigured_projects(mock_dependencies):
    """
    Test the 'Configure' flow when no unconfigured projects are found.
    """
    prompts_mock = mock_dependencies["prompts_instance"]
    discover_mock = mock_dependencies["discover"]
    init_project_mock = mock_dependencies["init_project"]
    
    # Sequence of choices: Configure -> Exit
    configure_choice = MagicMock(action="configure")
    exit_choice = MagicMock(action="exit")
    prompts_mock.ask_menu.side_effect = [configure_choice, exit_choice]
    prompts_mock.ask_text.return_value = "" # For the "Press Enter" pause

    # No unconfigured projects are found
    discover_mock.return_value = ([], [])

    # --- Run the function ---
    show_interactive_menu()
    
    # --- Assertions ---
    init_project_mock.assert_not_called()
    assert prompts_mock.ask_menu.call_count == 2 # Main menu, then main menu again to exit
    # Check that the pause prompt was called after the message
    prompts_mock.ask_text.assert_called_once_with("Press Enter to return to the main menu", default="")
