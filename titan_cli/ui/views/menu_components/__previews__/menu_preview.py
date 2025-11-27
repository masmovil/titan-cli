# ui/views/__previews__/menu_preview.py
from titan_cli.ui.views.menu_components import DynamicMenu, MenuRenderer

def display_menu_preview():
    """
    A non-interactive preview of what a menu looks like.
    """
    # 1. Build the menu dynamically using the fluent API
    dynamic_menu = DynamicMenu(title="Main Menu", emoji="🚀", tip="In interactive mode, you can use numbers to select an option.")
    
    dynamic_menu.add_category(name="Project Actions", emoji="📁") \
        .add_item(label="List Projects", description="List all configured projects.", action="projects:list") \
        .add_item(label="Initialize Project", description="Initialize a new Titan project.", action="projects:init")

    dynamic_menu.add_category(name="AI Actions", emoji="🤖") \
        .add_item(label="Chat with AI", description="Start a chat session with the AI.", action="ai:chat")

    # 2. Convert to a Pydantic Menu object
    menu = dynamic_menu.to_menu()

    # 3. Use MenuRenderer to display the menu
    menu_renderer = MenuRenderer()
    menu_renderer.render(menu)

    # 4. Indicate preview completion
    menu_renderer.text.info("Menu preview complete.", show_emoji=False)

if __name__ == "__main__":
    display_menu_preview()
