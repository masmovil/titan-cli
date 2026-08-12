# tests/engine/steps/test_ai_assistant_step.py
import unittest
from unittest.mock import patch, MagicMock
from titan_cli.ai.router import AIProviderType, AIRouteDecision
from titan_cli.ai.router.availability import AIProviderAvailability
from titan_cli.ai.router.resolver import AIRouteNeedsInput
from titan_cli.external_cli.launcher import CLILauncher
from titan_cli.engine.results import Error, Skip, Success
from titan_cli.engine.steps.ai_assistant_step import execute_ai_assistant_step

class TestCLILauncher(unittest.TestCase):

    @patch('shutil.which')
    def test_is_available_when_present(self, mock_which):
        mock_which.return_value = '/usr/bin/claude'
        launcher = CLILauncher('claude')
        self.assertTrue(launcher.is_available())

    @patch('shutil.which')
    def test_is_available_when_not_present(self, mock_which):
        mock_which.return_value = None
        launcher = CLILauncher('nonexistent')
        self.assertFalse(launcher.is_available())

    @patch('subprocess.run')
    def test_launch_no_prompt(self, mock_run):
        launcher = CLILauncher('my-cli')
        launcher.launch()
        mock_run.assert_called_once_with(
            ['my-cli'],
            stdin=unittest.mock.ANY,
            stdout=unittest.mock.ANY,
            stderr=unittest.mock.ANY,
            cwd=None
        )

    @patch('subprocess.run')
    def test_launch_with_positional_prompt(self, mock_run):
        launcher = CLILauncher('claude', prompt_flag=None)
        launcher.launch(prompt="hello")
        mock_run.assert_called_once_with(
            ['claude', 'hello'],
            stdin=unittest.mock.ANY,
            stdout=unittest.mock.ANY,
            stderr=unittest.mock.ANY,
            cwd=None
        )

    @patch('subprocess.run')
    def test_launch_with_flag_prompt(self, mock_run):
        launcher = CLILauncher('gemini', prompt_flag='-i')
        launcher.launch(prompt="world")
        mock_run.assert_called_once_with(
            ['gemini', '-i', 'world'],
            stdin=unittest.mock.ANY,
            stdout=unittest.mock.ANY,
            stderr=unittest.mock.ANY,
            cwd=None
        )


class TestExecuteAIAssistantStep(unittest.TestCase):
    """
    The step launches whatever the router resolved. It never asks which CLI to use -
    that is configured once, beforehand, in AI Configuration.
    """

    def setUp(self):
        self.mock_ctx = MagicMock()
        self.mock_ctx.data = {'test_failures': 'some error'}
        self.mock_step = MagicMock()
        self.mock_step.params = {'context_key': 'test_failures'}
        self.mock_ctx.textual = MagicMock()
        self.mock_ctx.textual.launch_external_cli = MagicMock(return_value=0)
        self.mock_ctx.textual.ask_confirm = MagicMock(return_value=True)
        self.mock_ctx.ai_router = self._router()

    @staticmethod
    def _router(*, interactive=("claude",), resolution="default"):
        router = MagicMock()
        router.availability.available_interactive_clis.return_value = [
            AIProviderAvailability(provider=AIProviderType.CLI_INTERACTIVE, identifier=name)
            for name in interactive
        ]
        if resolution == "default":
            resolution = AIRouteDecision(
                provider=AIProviderType.CLI_INTERACTIVE,
                cli=interactive[0] if interactive else None,
                reason="step default",
            )
        router.resolve.return_value = resolution
        return router

    def test_no_cli_installed_skips(self):
        """An environment with no CLI at all cannot do this - that is not an error."""
        self.mock_ctx.ai_router = self._router(interactive=())

        result = execute_ai_assistant_step(self.mock_step, self.mock_ctx)

        self.assertIsInstance(result, Skip)
        self.mock_ctx.textual.begin_step.assert_called_once()
        self.mock_ctx.textual.end_step.assert_called_once_with("skip")
        self.mock_ctx.textual.launch_external_cli.assert_not_called()

    def test_launches_the_resolved_cli(self):
        result = execute_ai_assistant_step(self.mock_step, self.mock_ctx)

        self.assertIsInstance(result, Success)
        call_kwargs = self.mock_ctx.textual.launch_external_cli.call_args.kwargs
        self.assertEqual(call_kwargs['cli_name'], 'claude')
        self.assertIn('some error', call_kwargs['prompt'])

    def test_never_asks_which_cli_even_with_several_installed(self):
        """Several installed CLIs is not a question - the configured default wins."""
        self.mock_ctx.ai_router = self._router(
            interactive=("claude", "gemini", "codex"),
            resolution=AIRouteDecision(
                provider=AIProviderType.CLI_INTERACTIVE, cli="gemini", reason="task preference"
            ),
        )

        result = execute_ai_assistant_step(self.mock_step, self.mock_ctx)

        self.assertIsInstance(result, Success)
        self.mock_ctx.textual.ask_option.assert_not_called()
        self.assertEqual(
            self.mock_ctx.textual.launch_external_cli.call_args.kwargs['cli_name'], 'gemini'
        )

    def test_unresolvable_route_errors_and_points_at_the_config_screen(self):
        """With CLIs installed but no default set, the step says exactly that."""
        self.mock_ctx.ai_router = self._router(
            interactive=("claude", "gemini"),
            resolution=AIRouteNeedsInput(reason="no default CLI is configured"),
        )

        result = execute_ai_assistant_step(self.mock_step, self.mock_ctx)

        self.assertIsInstance(result, Error)
        self.assertIn("no default CLI is configured", result.message)
        self.assertIn("AI Configuration", result.message)
        self.mock_ctx.textual.launch_external_cli.assert_not_called()

    def test_a_non_interactive_provider_errors_instead_of_launching(self):
        """A remote connection cannot drive a terminal session - say so, don't improvise."""
        self.mock_ctx.ai_router = self._router(
            resolution=AIRouteDecision(
                provider=AIProviderType.REMOTE, connection_id="work", reason="task preference"
            )
        )

        result = execute_ai_assistant_step(self.mock_step, self.mock_ctx)

        self.assertIsInstance(result, Error)
        self.mock_ctx.textual.launch_external_cli.assert_not_called()

    def test_ai_turned_off_skips_instead_of_launching(self):
        self.mock_ctx.ai_router = self._router(
            resolution=AIRouteDecision(provider=AIProviderType.OFF, reason="task preference")
        )

        result = execute_ai_assistant_step(self.mock_step, self.mock_ctx)

        self.assertIsInstance(result, Skip)
        self.mock_ctx.textual.launch_external_cli.assert_not_called()

    def test_step_never_persists_a_preference(self):
        """Persisting is the AI Configuration screen's job, not a step's."""
        execute_ai_assistant_step(self.mock_step, self.mock_ctx)

        self.mock_ctx.titan_config.upsert_task_ai_preference.assert_not_called()


if __name__ == '__main__':
    unittest.main()
