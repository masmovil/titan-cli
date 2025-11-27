# tests/ui/views/test_menu.py
import pytest
from unittest.mock import MagicMock, call
from titan_cli.ui.views.menu_components import Menu, MenuCategory, MenuItem, MenuRenderer

@pytest.fixture
def mock_console():
    """Fixture for a mocked Rich Console."""
    return MagicMock()

@pytest.fixture
def sample_menu():
    """Fixture for a sample Menu object."""
    return Menu(
        title="Test Menu",
        emoji="🧪",
        categories=[
            MenuCategory(
                name="Category 1",
                emoji="1️⃣",
                items=[
                    MenuItem(label="Item 1.1", description="Desc 1.1", action="action1_1"),
                    MenuItem(label="Item 1.2", description="Desc 1.2", action="action1_2"),
                ],
            ),
            MenuCategory(
                name="Category 2",
                emoji="2️⃣",
                items=[
                    MenuItem(label="Item 2.1", description="Desc 2.1", action="action2_1"),
                ],
            ),
        ],
        tip="This is a tip.",
    )

def test_menu_renderer_renders_correctly(mock_console, sample_menu):
    """
    Test that MenuRenderer correctly renders all parts of a menu.
    """
    # 1. Setup
    mock_text_renderer = MagicMock()
    mock_spacer_renderer = MagicMock()
    
    renderer = MenuRenderer(
        console=mock_console,
        text_renderer=mock_text_renderer,
        spacer_renderer=mock_spacer_renderer,
    )

    # 2. Action
    renderer.render(sample_menu)

    # 3. Assertions
    # Assert title is rendered
    mock_text_renderer.title.assert_called_once_with("🧪 Test Menu")
    
    # Assert category headers are rendered
    mock_text_renderer.body.assert_has_calls([
        call("1️⃣ Category 1", style="bold"),
        call("2️⃣ Category 2", style="bold"),
    ])
    
    # Assert menu items are printed
    expected_item_calls = [
        call("  [primary]1.[/primary] [bold]Item 1.1[/bold]"),
        call("     [dim]Desc 1.1[/dim]"),
        call("  [primary]2.[/primary] [bold]Item 1.2[/bold]"),
        call("     [dim]Desc 1.2[/dim]"),
        call("  [primary]3.[/primary] [bold]Item 2.1[/bold]"),
        call("     [dim]Desc 2.1[/dim]"),
    ]
    mock_console.print.assert_has_calls(expected_item_calls)

    # Assert tip is rendered
    mock_text_renderer.info.assert_called_once_with("This is a tip.", show_emoji=True)

    # Assert spacers are used
    assert mock_spacer_renderer.line.call_count > 0
