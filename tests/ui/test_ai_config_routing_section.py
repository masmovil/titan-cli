"""
Tests for the "AI per task" and "CLI" sections of the AI Configuration screen.

The pure aggregation logic is tested directly; the screen itself is also mounted for real,
because the two bugs the previous version of this screen shipped (a `compose_content` that
never yielded, and widget keys that collided) were both invisible to unit-level tests.
"""

import asyncio
from unittest.mock import MagicMock

from titan_cli.ai.router.availability import AIProviderAvailability
from titan_cli.ai.router.enums import AIProviderType
from titan_cli.ai.router.models import AIRouteDecision, AIRoutePolicy
from titan_cli.ai.router.resolver import AIRouteNeedsInput
from titan_cli.core.models import AIConfig, AIPreferences, AIProviderPreference
from titan_cli.core.workflows.ai_usage_discovery import (
    DiscoveredAIStep,
    DiscoveredWorkflowAIUsage,
)
from textual.widgets import Static

from titan_cli.ui.tui.app import TitanApp
from titan_cli.ui.tui.widgets import Button, StyledOptionList
from titan_cli.ui.tui.screens.ai_config import AIConfigScreen
from titan_cli.ui.tui.screens.ai_routing import (
    CliDefaultPicker,
    TaskRoutingRow,
    build_task_routings,
    executable_types,
    installed_clis,
    suggested_cli,
    task_label,
)


def _step(task, *, executes=(), preferred=None, enforces=True, name="a step", workflow="wf"):
    policy = AIRoutePolicy(
        task=task,
        executes=list(executes),
        preferred=list(preferred if preferred is not None else executes),
    )
    return DiscoveredAIStep(
        workflow_name=workflow,
        step_id=f"{task}-id",
        step_name=name,
        plugin="somewhere",
        step=task,
        policy=policy,
        enforces=enforces,
    )


class _StubResolver:
    """Stands in for AIRouteResolver, recording what it was asked to resolve."""

    def __init__(self, result=None):
        self.calls = []
        self.result = result

    def resolve(self, task, policy=None):
        self.calls.append((task, policy))
        return self.result


class TestExecutableTypes:
    def test_intersection_not_union(self):
        """
        One setting drives every step behind a task, so offering a type only some can run
        would configure a guaranteed failure for the rest.
        """
        steps = [
            _step("t", executes=[AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS]),
            _step("t", executes=[AIProviderType.REMOTE]),
        ]

        assert executable_types(steps) == [AIProviderType.REMOTE]

    def test_steps_declaring_nothing_add_no_constraint(self):
        """Silence is not "supports nothing" - it would empty the set for everyone else."""
        steps = [
            _step("t", executes=[AIProviderType.REMOTE]),
            _step("t", executes=[], enforces=False),
        ]

        assert executable_types(steps) == [AIProviderType.REMOTE]

    def test_all_silent_means_nothing_to_offer(self):
        assert executable_types([_step("t", executes=[], enforces=False)]) == []

    def test_off_is_never_a_declared_type(self):
        """Off is offered by the picker itself, not declared by a step."""
        types = executable_types([_step("t", executes=[AIProviderType.REMOTE])])

        assert AIProviderType.OFF not in types


class TestBuildTaskRoutings:
    def test_two_workflows_sharing_a_task_produce_one_row(self):
        usages = [
            DiscoveredWorkflowAIUsage(
                workflow_name="Commit A",
                steps=[_step("commit_message", executes=[AIProviderType.REMOTE])],
            ),
            DiscoveredWorkflowAIUsage(
                workflow_name="Commit B",
                steps=[_step("commit_message", executes=[AIProviderType.REMOTE])],
            ),
        ]

        routings = build_task_routings(usages, _StubResolver())

        assert len(routings) == 1
        assert routings[0].task == "commit_message"
        assert routings[0].workflows == ["Commit A", "Commit B"]

    def test_rows_carry_whether_a_preference_is_persisted(self):
        usages = [
            DiscoveredWorkflowAIUsage(
                workflow_name="wf", steps=[_step("commit_message", executes=[AIProviderType.REMOTE])]
            )
        ]

        routings = build_task_routings(usages, _StubResolver(), persisted_tasks=["commit_message"])

        assert routings[0].has_preference is True

    def test_a_declaring_but_not_enforcing_step_is_named(self):
        usages = [
            DiscoveredWorkflowAIUsage(
                workflow_name="wf",
                steps=[
                    _step(
                        "code_review_plan",
                        executes=[AIProviderType.CLI_HEADLESS],
                        enforces=False,
                        name="Review plan",
                    )
                ],
            )
        ]

        routings = build_task_routings(usages, _StubResolver())

        assert routings[0].unenforced_steps == ["Review plan"]

    def test_a_task_nothing_can_execute_is_not_configurable(self):
        usages = [
            DiscoveredWorkflowAIUsage(
                workflow_name="wf", steps=[_step("thread_resolution", executes=[], enforces=False)]
            )
        ]

        routings = build_task_routings(usages, _StubResolver())

        assert routings[0].configurable is False
        assert routings[0].needs_setup is True

    def test_an_unresolvable_row_needs_setup_even_though_it_is_configurable(self):
        """A stored preference the step can't run is the main case this marking exists for."""
        usages = [
            DiscoveredWorkflowAIUsage(
                workflow_name="wf",
                steps=[_step("code_review_findings", executes=[AIProviderType.CLI_HEADLESS])],
            )
        ]
        resolver = _StubResolver(AIRouteNeedsInput(reason="the configured provider is 'remote'"))

        routings = build_task_routings(usages, resolver)

        assert routings[0].configurable is True
        assert routings[0].needs_setup is True

    def test_a_resolved_row_does_not_need_setup(self):
        usages = [
            DiscoveredWorkflowAIUsage(
                workflow_name="wf",
                steps=[_step("commit_message", executes=[AIProviderType.CLI_HEADLESS])],
            )
        ]
        resolver = _StubResolver(
            AIRouteDecision(provider=AIProviderType.CLI_HEADLESS, cli="claude", reason="default")
        )

        routings = build_task_routings(usages, resolver)

        assert routings[0].needs_setup is False

    def test_resolution_previews_with_what_all_steps_can_run(self):
        """The preview must reflect the same constraint the picker enforces."""
        usages = [
            DiscoveredWorkflowAIUsage(
                workflow_name="wf",
                steps=[
                    _step(
                        "commit_message",
                        executes=[AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS],
                        preferred=[AIProviderType.CLI_HEADLESS, AIProviderType.REMOTE],
                    ),
                    _step("commit_message", executes=[AIProviderType.REMOTE]),
                ],
            )
        ]
        resolver = _StubResolver()

        build_task_routings(usages, resolver)

        _task, policy = resolver.calls[0]
        assert policy.executes == [AIProviderType.REMOTE]
        assert policy.preferred == [AIProviderType.REMOTE]


class TestCliDefaults:
    def test_the_same_cli_in_both_modes_is_listed_once(self):
        headless = [AIProviderAvailability(provider=AIProviderType.CLI_HEADLESS, identifier="claude")]
        interactive = [
            AIProviderAvailability(provider=AIProviderType.CLI_INTERACTIVE, identifier="claude"),
            AIProviderAvailability(provider=AIProviderType.CLI_INTERACTIVE, identifier="gemini"),
        ]

        assert installed_clis(headless, interactive) == ["claude", "gemini"]

    def test_a_single_installed_cli_is_suggested(self):
        assert suggested_cli(["claude"], None) == "claude"

    def test_nothing_is_suggested_among_several(self):
        """With a real choice to make, suggesting one would be choosing for the user."""
        assert suggested_cli(["claude", "gemini"], None) is None

    def test_nothing_is_suggested_once_a_default_exists(self):
        assert suggested_cli(["claude"], "claude") is None


class TestTaskLabels:
    def test_known_tasks_read_as_english(self):
        assert task_label("commit_message") == "Commit messages"

    def test_an_unknown_community_task_still_reads(self):
        assert task_label("my_plugin_thing") == "My plugin thing"


class TestScreenMounts:
    """
    Mount the real screen. Kept synchronous so it needs no async test plugin - the repo has
    none, and this is the only place that needs an event loop.
    """

    @staticmethod
    def _config(*, default_cli=None, tasks=None):
        config = MagicMock()
        config.config.ai = AIConfig(
            default_cli=default_cli,
            preferences=AIPreferences(
                tasks={t: AIProviderPreference(provider=p) for t, p in (tasks or {}).items()}
            ),
        )
        config.get_project_name.return_value = "test-project"
        return config

    @staticmethod
    def _stub_screen_dependencies(monkeypatch, usages, clis):
        """Replace discovery and provider probing so a mount needs no machine state."""
        monkeypatch.setattr(
            "titan_cli.ui.tui.screens.ai_config.AIUsageDiscoveryService",
            lambda **kwargs: MagicMock(discover_all=lambda: usages),
        )

        class _Checker:
            def __init__(self, *args, **kwargs):
                pass

            def available_remote_connections(self):
                return []

            def available_headless_clis(self):
                return [
                    AIProviderAvailability(
                        provider=AIProviderType.CLI_HEADLESS, identifier=name
                    )
                    for name in clis
                ]

            def available_interactive_clis(self):
                return [
                    AIProviderAvailability(
                        provider=AIProviderType.CLI_INTERACTIVE, identifier=name
                    )
                    for name in clis
                ]

            def is_provider_available(self, provider):
                return provider != AIProviderType.REMOTE

        monkeypatch.setattr(
            "titan_cli.ui.tui.screens.ai_config.AIAvailabilityChecker", _Checker
        )

    @classmethod
    def _mount(cls, config, usages, monkeypatch, *, clis=("claude",)):
        """Mount AIConfigScreen and read back what it rendered."""
        cls._stub_screen_dependencies(monkeypatch, usages, clis)

        captured = {}

        async def run():
            app = TitanApp(config, initial_screen=lambda: AIConfigScreen(config))
            async with app.run_test() as pilot:
                await pilot.pause()
                # Read everything while the app is still running: querying a widget after
                # the test app shuts down finds nothing, which reads as a missing button.
                captured["tasks"] = [
                    r.routing.task for r in app.screen.query(TaskRoutingRow)
                ]
                captured["buttons"] = {
                    r.routing.task: [b.id for b in r.query(Button)]
                    for r in app.screen.query(TaskRoutingRow)
                }
                pickers = app.screen.query(CliDefaultPicker)
                captured["clis"] = [
                    (name, name == p.current, name == p.suggestion)
                    for p in pickers
                    for name in p.installed
                ]

        asyncio.run(run())
        return captured

    def test_one_row_per_task_and_one_row_per_installed_cli(self, monkeypatch):
        usages = [
            DiscoveredWorkflowAIUsage(
                workflow_name="wf",
                steps=[
                    _step("commit_message", executes=[AIProviderType.CLI_HEADLESS]),
                    _step("generic_assistant", executes=[AIProviderType.CLI_INTERACTIVE]),
                ],
            )
        ]

        captured = self._mount(
            self._config(default_cli="claude"), usages, monkeypatch, clis=("claude", "gemini")
        )

        assert captured["tasks"] == ["generic_assistant", "commit_message"]
        assert captured["clis"] == [
            ("claude", True, False),
            ("gemini", False, False),
        ]

    def test_a_task_with_no_choice_offers_no_actions_at_all(self, monkeypatch):
        """
        Offering Change or Clear where nothing can take effect invites the user to configure
        a setting no step will read. The row says so instead.
        """
        usages = [
            DiscoveredWorkflowAIUsage(
                workflow_name="wf",
                steps=[_step("code_review_plan", executes=[], enforces=False)],
            )
        ]

        captured = self._mount(
            self._config(default_cli="claude"),
            usages,
            monkeypatch,
        )

        assert captured["buttons"] == {"code_review_plan": []}

    def test_an_unconfigurable_task_with_a_saved_preference_still_offers_clear(
        self, monkeypatch
    ):
        """
        A preference persisted while the task was routable would silently re-apply if the
        task becomes routable again - the row must keep offering the way to remove it.
        """
        usages = [
            DiscoveredWorkflowAIUsage(
                workflow_name="wf",
                steps=[_step("code_review_plan", executes=[], enforces=False)],
            )
        ]

        captured = self._mount(
            self._config(default_cli="claude", tasks={"code_review_plan": "remote"}),
            usages,
            monkeypatch,
        )

        assert captured["buttons"] == {"code_review_plan": ["task-clear-code_review_plan"]}

    def test_a_configurable_task_offers_change_and_clear(self, monkeypatch):
        usages = [
            DiscoveredWorkflowAIUsage(
                workflow_name="wf",
                steps=[_step("commit_message", executes=[AIProviderType.CLI_HEADLESS])],
            )
        ]

        captured = self._mount(
            self._config(default_cli="claude", tasks={"commit_message": "cli_headless"}),
            usages,
            monkeypatch,
        )

        assert captured["buttons"] == {
            "commit_message": ["task-change-commit_message", "task-clear-commit_message"]
        }

    def test_a_lone_installed_cli_is_suggested_when_no_default_is_set(self, monkeypatch):
        captured = self._mount(self._config(), [], monkeypatch, clis=("claude",))

        assert captured["clis"] == [("claude", False, True)]

    def test_a_stale_default_warns_instead_of_reading_as_active(self, monkeypatch):
        """
        A saved default that is no longer installed must not show the success line while
        the switch highlights a different, fallback CLI.
        """
        config = self._config(default_cli="claude")
        self._stub_screen_dependencies(monkeypatch, [], ("gemini", "codex"))

        result = {}

        async def run():
            app = TitanApp(config, initial_screen=lambda: AIConfigScreen(config))
            async with app.run_test() as pilot:
                await pilot.pause()
                picker = app.screen.query_one(CliDefaultPicker)
                result["current"] = picker.current
                result["status"] = str(
                    app.screen.query_one("#cli-status", Static).renderable
                )

        asyncio.run(run())

        assert result["current"] is None
        assert "claude" in result["status"]
        assert "no longer installed" in result["status"]

    def test_screen_survives_having_nothing_to_show(self, monkeypatch):
        captured = self._mount(self._config(), [], monkeypatch, clis=())

        assert captured["tasks"] == []
        assert captured["clis"] == []

    def test_selecting_a_cli_saves_and_keeps_the_user_where_they_are(self, monkeypatch):
        """
        Selecting from the list IS the choice, so it saves on Enter - which means it
        must not rebuild the control the user is operating, or their next keypress goes
        nowhere.
        """
        config = self._config()
        saved = []
        config.set_default_ai_cli.side_effect = saved.append
        self._stub_screen_dependencies(monkeypatch, [], ("claude", "gemini", "codex"))

        result = {}

        async def run():
            app = TitanApp(config, initial_screen=lambda: AIConfigScreen(config))
            async with app.run_test() as pilot:
                await pilot.pause()
                screen = app.screen
                result["before"] = str(screen.query_one("#cli-status", Static).renderable)
                cli_list = screen.query_one("#cli-default-list", StyledOptionList)
                cli_list.focus()
                cli_list.highlighted = 1
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                result["after"] = str(screen.query_one("#cli-status", Static).renderable)
                result["focus_kept"] = screen.focused is cli_list

        asyncio.run(run())

        assert saved == ["gemini"]
        assert "No default set yet" in result["before"]
        assert "gemini" in result["after"]
        assert result["focus_kept"]

    def test_confirming_the_only_installed_cli_saves_it(self, monkeypatch):
        """
        With one CLI installed the list pre-highlights it as a suggestion, so the only
        possible pick selects the already-highlighted row - that confirmation must save.
        """
        config = self._config()
        saved = []
        config.set_default_ai_cli.side_effect = saved.append
        self._stub_screen_dependencies(monkeypatch, [], ("claude",))

        result = {}

        async def run():
            app = TitanApp(config, initial_screen=lambda: AIConfigScreen(config))
            async with app.run_test() as pilot:
                await pilot.pause()
                screen = app.screen
                result["before"] = str(screen.query_one("#cli-status", Static).renderable)
                cli_list = screen.query_one("#cli-default-list", StyledOptionList)
                cli_list.focus()
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                result["after"] = str(screen.query_one("#cli-status", Static).renderable)

        asyncio.run(run())

        assert saved == ["claude"]
        assert "No default set yet" in result["before"]
        assert "Titan will run claude" in result["after"]
