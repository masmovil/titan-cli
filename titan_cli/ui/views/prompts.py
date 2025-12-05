"""
Prompts Component (View)

Class-based, theme-aware wrapper for rich.prompt. This is considered a 'view'
because it is a composite component that uses other components (like TextRenderer)
to display its own UI (e.g., error messages).
"""
import os
import sys
import subprocess
import tempfile
from pathlib import Path
import platform
from typing import Optional, List, Callable, Tuple
from rich.console import Console
from rich.prompt import Prompt, Confirm, IntPrompt
from ..console import get_console
from ..components.typography import TextRenderer
from ...messages import msg # Import messages
from .menu_components import Menu, MenuItem, MenuRenderer # Import Menu, MenuItem, MenuRenderer from the new package

class PromptsRenderer:
    """
    Reusable wrapper for rich.prompt with theme-aware styling and validation.
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        text_renderer: Optional[TextRenderer] = None,
        menu_renderer: Optional[MenuRenderer] = None,
    ):
        """
        Initializes the PromptsRenderer.

        Args:
            console: A Rich Console instance. If None, uses the global theme-aware console.
            text_renderer: An instance of TextRenderer for displaying messages.
                           If None, a default instance is created.
            menu_renderer: An instance of MenuRenderer for displaying menus.
                           If None, a default instance is created.
        """
        if console is None:
            console = get_console()
        self.console = console

        if text_renderer is None:
            text_renderer = TextRenderer(console=self.console)
        self.text = text_renderer

        if menu_renderer is None:
            menu_renderer = MenuRenderer(console=self.console, text_renderer=self.text)
        self.menu_renderer = menu_renderer


    def ask_text(
        self,
        prompt: str,
        default: str = "",
        password: bool = False,
        validator: Optional[Callable[[str], bool]] = None
    ) -> str:
        """
        Ask for text input.
        """
        while True:
            value = Prompt.ask(
                prompt,
                default=default if default else None,
                password=password,
                console=self.console
            )

            if validator and not validator(value):
                self.text.error(msg.Prompts.INVALID_INPUT, show_emoji=False)
                continue

            return value

    def ask_multiline(
        self, 
        prompt: str,
        default: str = "",
        template: Optional[str] = None
    ) -> str:
        """
        Open external editor for multi-line input (cross-platform).
        
        Falls back to inline input if editor fails.
        """
        self.text.info(prompt)

        # Intentar con editor externo
        try:
            return self._ask_multiline_editor(default or template or "")
        except Exception as e:
            # Fallback a input inline
            self.text.warning(f"Could not open editor: {e}")
            return self._ask_multiline_inline(default or template or "")

    def _get_editor(self) -> str:
        """Get appropriate editor for current platform."""
        # 1. User preference
        if editor := os.environ.get('EDITOR') or os.environ.get('VISUAL'):
            return editor

        # 2. Platform defaults
        system = platform.system()

        if system == 'Windows':
            # Intentar editores comunes en Windows
            for editor in ['code --wait', 'notepad++', 'notepad']:
                try:
                    # Check si existe
                    cmd = editor.split()[0]
                    if system == 'Windows':
                        cmd += '.exe' if not cmd.endswith('.exe') else ''

                    # Verificar que existe
                    subprocess.run(['where' if system == 'Windows' else 'which', cmd],
                                   capture_output=True, check=True)
                    return editor
                except subprocess.CalledProcessError:
                    continue

            # Fallback final
            return 'notepad'

        elif system == 'Darwin':  # macOS
            # Preferir nano por ser más user-friendly
            return 'nano'

        else:  # Linux y otros
            return 'nano'

    def _ask_multiline_editor(self, content: str) -> str:
        """Open external editor."""
        editor_cmd = self._get_editor()

        # Create temp file
        with tempfile.NamedTemporaryFile(
            mode='w+',
            suffix='.md',
            delete=False,
            encoding='utf-8'
        ) as tf:
            temp_path = tf.name
            if content:
                tf.write(content)
                tf.flush()

        try:
            self.text.body(f"Opening {editor_cmd}... (save and close to continue)", style="dim")

            # Ejecutar editor
            if platform.system() == 'Windows':
                # Windows requiere manejo especial
                subprocess.run(editor_cmd, shell=True, check=True)
            else:
                # Unix-like
                subprocess.run(editor_cmd.split() + [temp_path], check=True)

            # Leer resultado
            with open(temp_path, 'r', encoding='utf-8') as f:
                result = f.read().strip()

            return result

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def _ask_multiline_inline(self, default: str = "") -> str:
        """Fallback: multi-line input in terminal."""
        self.text.body("(Press Ctrl+D on Unix / Ctrl+Z then Enter on Windows to finish):", style="dim")

        lines = []
        if default:
            lines = default.split('\n')
            # Mostrar contenido por defecto
            for line in lines:
                self.console.print(f"  {line}", style="dim")

        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass

        return '\n'.join(lines).strip()

    def ask_confirm(
        self,
        question: str,
        default: bool = False
    ) -> bool:
        """
        Ask for yes/no confirmation.
        """
        return Confirm.ask(question, default=default, console=self.console)

    def ask_choice(
        self,
        question: str,
        choices: List[str],
        default: Optional[str] = None
    ) -> str:
        """
        Ask user to choose from a list of options.
        """
        return Prompt.ask(
            question,
            choices=choices,
            default=default,
            console=self.console
        )

    def ask_int(
        self,
        question: str,
        default: Optional[int] = None,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None
    ) -> int:
        """
        Ask for integer input.
        """
        while True:
            # IntPrompt itself handles non-integer input by re-prompting.
            # The TypeError occurred if the user just hits Enter with no default.
            value = IntPrompt.ask(question, default=default, console=self.console)
            
            # Handle case where user hits Enter without input and no default is set
            if value is None:
                self.text.error(msg.Prompts.MISSING_VALUE, show_emoji=False)
                continue

            if min_value is not None and value < min_value:
                self.text.error(msg.Prompts.VALUE_TOO_LOW.format(min=min_value), show_emoji=False)
                continue

            if max_value is not None and value > max_value:
                self.text.error(msg.Prompts.VALUE_TOO_HIGH.format(max=max_value), show_emoji=False)
                continue

            return value

    def ask_menu(
        self,
        menu: Menu,
        allow_quit: bool = True
    ) -> Optional[MenuItem]:
        """
        Displays a menu and asks the user to choose an item.

        Args:
            menu: The Menu object to display.
            allow_quit: If True, allows the user to quit by entering 'q'.

        Returns:
            The selected MenuItem, or None if the user quits.
        """
        self.menu_renderer.render(menu)

        total_items = sum(len(cat.items) for cat in menu.categories)
        if total_items == 0:
            return None

        prompt = "Select an option"
        if allow_quit:
            prompt += " (or 'q' to quit)"

        while True:
            choice_str = Prompt.ask(prompt, console=self.console)

            if allow_quit and choice_str.lower() == 'q':
                return None

            try:
                choice = int(choice_str)
                if 1 <= choice <= total_items:
                    # Find the selected item
                    item_count = 0
                    for category in menu.categories:
                        for item in category.items:
                            item_count += 1
                            if item_count == choice:
                                return item
                else:
                    self.text.error(msg.Prompts.INVALID_MENU_CHOICE.format(total_items=total_items))
            except ValueError:
                self.text.error(msg.Prompts.NOT_A_NUMBER, show_emoji=False)
