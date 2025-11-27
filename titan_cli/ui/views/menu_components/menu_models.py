# ui/views/menu_models.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class MenuItem(BaseModel):
    """Represents an individual menu item."""
    label: str = Field(..., description="The display text for the menu item.")
    description: str = Field(..., description="A short description of what the item does.")
    action: str = Field(..., description="The action identifier associated with this item.")

class MenuCategory(BaseModel):
    """Represents a category of menu items."""
    name: str = Field(..., description="The name of the category.")
    emoji: str = Field(..., description="An emoji to display next to the category name.")
    items: List[MenuItem] = Field(..., description="A list of menu items in this category.")

class Menu(BaseModel):
    """Represents a complete menu with categories."""
    title: str = Field(..., description="The title of the menu.")
    emoji: str = Field(..., description="An emoji to display next to the menu title.")
    categories: List[MenuCategory] = Field(..., description="A list of categories in the menu.")
    tip: Optional[str] = Field(None, description="An optional tip to display at the bottom of the menu.")
