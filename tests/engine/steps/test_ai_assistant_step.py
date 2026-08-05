# tests/engine/steps/test_ai_assistant_step.py
import unittest
from unittest.mock import patch, MagicMock
from titan_cli.ai.router import AIProviderType, AIRouteDecision
from titan_cli.external_cli.launcher import CLILauncher
from titan_cli.engine.results import Skip, Success
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

    def setUp(self):
        self.mock_ctx = MagicMock()
        self.mock_ctx.data = {'test_failures': 'some error'}
        self.mock_step = MagicMock()
        self.mock_step.params = {'context_key': 'test_failures'}
        # Mock textual UI components
        self.mock_ctx.textual = MagicMock()
        self.mock_ctx.textual.launch_external_cli = MagicMock(return_value=0)

    @patch('shutil.which', return_value=None)
    def test_no_cli_available(self, mock_which):
        result = execute_ai_assistant_step(self.mock_step, self.mock_ctx)
        self.assertIsInstance(result, Skip)
        # Verify that step container was started and ended
        self.mock_ctx.textual.begin_step.assert_called_once()
        self.mock_ctx.textual.end_step.assert_called_once_with("skip")

    @patch('shutil.which', side_effect=lambda cli: '/usr/bin/claude' if cli == 'claude' else None)
    def test_one_cli_available(self, mock_which):
        # Mock the confirmation dialog to return True
        self.mock_ctx.textual.ask_confirm = MagicMock(return_value=True)

        result = execute_ai_assistant_step(self.mock_step, self.mock_ctx)
        self.assertIsInstance(result, Success)

        # Verify launch_external_cli was called with the expected prompt
        self.mock_ctx.textual.launch_external_cli.assert_called_once()
        call_kwargs = self.mock_ctx.textual.launch_external_cli.call_args.kwargs
        self.assertEqual(call_kwargs['cli_name'], 'claude')
        self.assertIn('some error', call_kwargs['prompt'])


    @patch('shutil.which', return_value='/usr/bin/some_cli')
    def test_multiple_clis_available_select_one(self, mock_which):
        # Mock user confirming and picking gemini from the option list
        self.mock_ctx.textual.ask_confirm = MagicMock(return_value=True)
        self.mock_ctx.textual.ask_option = MagicMock(return_value="gemini")

        result = execute_ai_assistant_step(self.mock_step, self.mock_ctx)
        self.assertIsInstance(result, Success)

        # Check that the user was asked to select from a proper option list
        self.mock_ctx.textual.ask_option.assert_called_once()
        call_kwargs = self.mock_ctx.textual.ask_option.call_args.kwargs
        option_values = [opt.value for opt in call_kwargs['options']]
        self.assertIn('gemini', option_values)

        # Check that launch_external_cli was called with gemini
        self.mock_ctx.textual.launch_external_cli.assert_called_once()
        call_kwargs = self.mock_ctx.textual.launch_external_cli.call_args.kwargs
        self.assertEqual(call_kwargs['cli_name'], 'gemini')


    @patch('shutil.which', return_value='/usr/bin/some_cli')
    def test_multiple_clis_available_cancel(self, mock_which):
        # Mock user confirming but then cancelling selection (no option picked)
        self.mock_ctx.textual.ask_confirm = MagicMock(return_value=True)
        self.mock_ctx.textual.ask_option = MagicMock(return_value=None)

        result = execute_ai_assistant_step(self.mock_step, self.mock_ctx)
        self.assertIsInstance(result, Skip)

        # Verify that ask_option was called to get user's selection
        self.mock_ctx.textual.ask_option.assert_called_once()

        # Verify that launch_external_cli was NOT called
        self.mock_ctx.textual.launch_external_cli.assert_not_called()

    @patch('shutil.which', return_value='/usr/bin/some_cli')
    def test_configured_cli_is_used_without_asking(self, mock_which):
        """A resolved interactive CLI means the user already chose - don't ask again."""
        self.mock_ctx.textual.ask_confirm = MagicMock(return_value=True)
        self.mock_ctx.textual.ask_option = MagicMock(return_value="claude")
        self.mock_ctx.ai_router.resolve = MagicMock(
            return_value=AIRouteDecision(
                provider=AIProviderType.CLI_INTERACTIVE, cli="gemini", reason="task preference"
            )
        )

        result = execute_ai_assistant_step(self.mock_step, self.mock_ctx)

        self.assertIsInstance(result, Success)
        self.mock_ctx.textual.ask_option.assert_not_called()
        call_kwargs = self.mock_ctx.textual.launch_external_cli.call_args.kwargs
        self.assertEqual(call_kwargs['cli_name'], 'gemini')

    @patch('shutil.which', return_value='/usr/bin/some_cli')
    def test_ai_turned_off_skips_instead_of_launching(self, mock_which):
        self.mock_ctx.textual.ask_confirm = MagicMock(return_value=True)
        self.mock_ctx.ai_router.resolve = MagicMock(
            return_value=AIRouteDecision(provider=AIProviderType.OFF, reason="task preference")
        )

        result = execute_ai_assistant_step(self.mock_step, self.mock_ctx)

        self.assertIsInstance(result, Skip)
        self.mock_ctx.textual.launch_external_cli.assert_not_called()

    @patch('shutil.which', return_value='/usr/bin/some_cli')
    def test_step_never_persists_a_preference(self, mock_which):
        """Persisting is the AI Configuration screen's job, not a step's."""
        self.mock_ctx.textual.ask_confirm = MagicMock(return_value=True)
        self.mock_ctx.textual.ask_option = MagicMock(return_value="gemini")

        execute_ai_assistant_step(self.mock_step, self.mock_ctx)

        self.mock_ctx.titan_config.upsert_task_ai_preference.assert_not_called()


if __name__ == '__main__':
    unittest.main()