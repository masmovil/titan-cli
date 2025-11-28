# tests/test_cli.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import typer

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
    Test the full 'Configure a New Project' flow.
    - User selects 'configure'.
    - A list of unconfigured projects is shown.
    - User selects a project.
    - initialize_project is called.
    """
    prompts_mock = mock_dependencies["prompts_instance"]
    discover_mock = mock_dependencies["discover"]
    init_project_mock = mock_dependencies["init_project"]

    # --- Simulation Setup ---
    # 1. Main menu choice: user selects 'configure'
    main_menu_choice = MagicMock()
    main_menu_choice.action = "configure"

    # 2. Unconfigured projects are discovered
    unconfigured_path = Path("/fake/projects/new-project")
    discover_mock.return_value = ([], [unconfigured_path])

    # 3. Project selection menu: user selects the new project
    project_menu_choice = MagicMock()
    project_menu_choice.action = str(unconfigured_path.resolve())
    
    # prompts.ask_menu will be called twice. 
    # First time for the main menu, second for the project selection.
    prompts_mock.ask_menu.side_effect = [main_menu_choice, project_menu_choice]

    # --- Run the function ---
    show_interactive_menu()

    # --- Assertions ---
    # Check that discovery was called
    discover_mock.assert_called_once_with("/fake/projects")

    # Check that ask_menu was called twice
    assert prompts_mock.ask_menu.call_count == 2
    
    # Check that initialize_project was called with the correct path
    init_project_mock.assert_called_once_with(unconfigured_path.resolve())


def test_show_interactive_menu_list_flow(mock_dependencies):
    """
    Test the 'List Configured Projects' flow.
    - User selects 'list'.
    - list_projects is called.
    """
    prompts_mock = mock_dependencies["prompts_instance"]
    list_projects_mock = mock_dependencies["list_projects"]

    # 1. Main menu choice: user selects 'list'
    main_menu_choice = MagicMock()
    main_menu_choice.action = "list"
    prompts_mock.ask_menu.return_value = main_menu_choice

    # --- Run the function ---
    show_interactive_menu()

    # --- Assertions ---
    list_projects_mock.assert_called_once()

def test_show_interactive_menu_no_unconfigured_projects(mock_dependencies):
    """
    Test the 'Configure' flow when no unconfigured projects are found.
    """
    prompts_mock = mock_dependencies["prompts_instance"]
    discover_mock = mock_dependencies["discover"]
    init_project_mock = mock_dependencies["init_project"]
    
    # 1. Main menu choice: user selects 'configure'
    main_menu_choice = MagicMock()
    main_menu_choice.action = "configure"
    prompts_mock.ask_menu.return_value = main_menu_choice
    
    # 2. No unconfigured projects are found
    discover_mock.return_value = ([], [])

    # --- Run the function ---
    # We need to wrap this in a pytest.raises since a clean exit is a SystemExit
    with pytest.raises(typer.Exit) as e:
        show_interactive_menu()

    # Assert that the exit code is 0 (success)
    assert e.value.exit_code == 0
    
    # Check that initialize_project was NOT called
    init_project_mock.assert_not_called()
