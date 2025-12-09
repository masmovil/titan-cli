# ui/views/dynamic_menu.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
from .menu_models import Menu, MenuCategory, MenuItem

class CategoryBuilder:
    """
    A helper class to build categories in a fluent way.
    """
    def __init__(self, menu: DynamicMenu, category_index: int):
        self.menu = menu
        self.category_index = category_index

    def add_item(self, label: str, description: str, action: str) -> CategoryBuilder:
        """
        Adds a new item to the category and returns the builder instance for chaining.
        """
        self.menu.add_item(self.category_index, label, description, action)
        return self

class DynamicMenu:
    """
    A helper class to build Menu objects programmatically.
    """

    def __init__(self, title: str, emoji: str = "📋", tip: Optional[str] = None):
        self.title = title
        self.emoji = emoji
        self.tip = tip
        self.categories: List[Dict[str, Any]] = []
        self.top_level_items: List[Dict[str, Any]] = [] # NEW: For items added directly to the menu

    def add_category(self, name: str, emoji: str = "📁") -> CategoryBuilder:
        """
        Adds a new category to the menu.

        Returns:
            A CategoryBuilder instance for chaining.
        """
        category = {"name": name, "emoji": emoji, "items": []}
        self.categories.append(category)
        return CategoryBuilder(self, len(self.categories) - 1)

    def add_item(self, category_index: int, label: str, description: str, action: str):
        """
        Adds a new item to the specified category.
        This is primarily an internal method used by `CategoryBuilder`.
        """
        if not (0 <= category_index < len(self.categories)):
            raise IndexError("Category index out of range.")
        
        item = {
            "label": label,
            "description": description,
            "action": action,
        }
        self.categories[category_index]["items"].append(item)

    # NEW: Method to add items directly to the menu (not within a category)
    def add_top_level_item(self, label: str, description: str, action: str) -> "DynamicMenu":
        """
        Adds a new item directly to the top level of the menu.
        """
        item = {"label": label, "description": description, "action": action}
        self.top_level_items.append(item)
        return self

    def to_menu(self) -> Menu:
        """
        Converts the dynamic menu structure to a Pydantic Menu model.
        If top-level items were added, they will appear first under a nameless category.

        Returns:
            A Menu object.
        """
        all_rendered_categories = []
        # Prepend top-level items in a nameless category if they exist
        if self.top_level_items:
            # We explicitly pass the list of MenuItem objects to the MenuCategory constructor
            top_level_menu_items = [MenuItem(**item_dict) for item_dict in self.top_level_items]
            all_rendered_categories.append(MenuCategory(name="", emoji="", items=top_level_menu_items))
        
        # Extend with existing categories
        all_rendered_categories.extend([MenuCategory(**cat) for cat in self.categories])

        return Menu(
            title=self.title,
            emoji=self.emoji,
            tip=self.tip,
            categories=all_rendered_categories
        )
