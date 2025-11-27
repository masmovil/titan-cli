# ui/views/dynamic_menu.py
from typing import List, Dict, Any, Optional
from .menu_models import Menu, MenuCategory, MenuItem

class DynamicMenu:
    """
    A helper class to build Menu objects programmatically.
    """

    def __init__(self, title: str, emoji: str = "📋", tip: Optional[str] = None):
        self.title = title
        self.emoji = emoji
        self.tip = tip
        self.categories: List[Dict[str, Any]] = []

    def add_category(self, name: str, emoji: str = "📁") -> int:
        """
        Adds a new category to the menu.

        Returns:
            The index of the newly added category.
        """
        category = {"name": name, "emoji": emoji, "items": []}
        self.categories.append(category)
        return len(self.categories) - 1

    def add_item(self, category_index: int, label: str, description: str, action: str):
        """
        Adds a new item to the specified category.
        """
        if not (0 <= category_index < len(self.categories)):
            raise IndexError("Category index out of range.")
        
        item = {
            "label": label,
            "description": description,
            "action": action,
        }
        self.categories[category_index]["items"].append(item)

    def to_menu(self) -> Menu:
        """
        Converts the dynamic menu structure to a Pydantic Menu model.

        Returns:
            A Menu object.
        """
        return Menu(
            title=self.title,
            emoji=self.emoji,
            tip=self.tip,
            categories=[MenuCategory(**cat) for cat in self.categories]
        )
