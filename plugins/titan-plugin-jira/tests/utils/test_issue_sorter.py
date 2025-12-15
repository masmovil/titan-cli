"""
Tests for IssueSorter utility
"""

from titan_plugin_jira.utils import IssueSorter, IssueSortConfig


class MockIssue:
    """Mock JIRA issue for testing."""

    def __init__(self, key: str, status: str, priority: str):
        self.key = key
        self.status = status
        self.priority = priority


class TestIssueSortConfig:
    """Tests for IssueSortConfig."""

    def test_default_config_has_status_order(self):
        """Default config should have status order mappings."""
        config = IssueSortConfig.default()

        assert "to do" in config.status_order
        assert "in progress" in config.status_order
        assert "done" in config.status_order

    def test_default_config_has_priority_order(self):
        """Default config should have priority order mappings."""
        config = IssueSortConfig.default()

        assert "critical" in config.priority_order
        assert "high" in config.priority_order
        assert "medium" in config.priority_order
        assert "low" in config.priority_order

    def test_status_order_progression(self):
        """Status order should progress from To Do → In Progress → Done."""
        config = IssueSortConfig.default()

        assert config.status_order["to do"] < config.status_order["in progress"]
        assert config.status_order["in progress"] < config.status_order["done"]

    def test_priority_order_progression(self):
        """Priority order should progress from Critical → High → Medium → Low."""
        config = IssueSortConfig.default()

        assert config.priority_order["critical"] < config.priority_order["high"]
        assert config.priority_order["high"] < config.priority_order["medium"]
        assert config.priority_order["medium"] < config.priority_order["low"]


class TestIssueSorter:
    """Tests for IssueSorter."""

    def test_sort_by_status(self):
        """Issues should be sorted by status first."""
        issues = [
            MockIssue("PROJ-3", "Done", "High"),
            MockIssue("PROJ-1", "To Do", "High"),
            MockIssue("PROJ-2", "In Progress", "High"),
        ]

        sorter = IssueSorter()
        sorted_issues = sorter.sort(issues)

        assert sorted_issues[0].key == "PROJ-1"  # To Do
        assert sorted_issues[1].key == "PROJ-2"  # In Progress
        assert sorted_issues[2].key == "PROJ-3"  # Done

    def test_sort_by_priority_within_same_status(self):
        """Within same status, issues should be sorted by priority."""
        issues = [
            MockIssue("PROJ-1", "To Do", "Low"),
            MockIssue("PROJ-2", "To Do", "Critical"),
            MockIssue("PROJ-3", "To Do", "High"),
        ]

        sorter = IssueSorter()
        sorted_issues = sorter.sort(issues)

        assert sorted_issues[0].key == "PROJ-2"  # Critical
        assert sorted_issues[1].key == "PROJ-3"  # High
        assert sorted_issues[2].key == "PROJ-1"  # Low

    def test_sort_by_key_within_same_status_and_priority(self):
        """Within same status and priority, issues should be sorted by key."""
        issues = [
            MockIssue("PROJ-300", "To Do", "High"),
            MockIssue("PROJ-100", "To Do", "High"),
            MockIssue("PROJ-200", "To Do", "High"),
        ]

        sorter = IssueSorter()
        sorted_issues = sorter.sort(issues)

        assert sorted_issues[0].key == "PROJ-100"
        assert sorted_issues[1].key == "PROJ-200"
        assert sorted_issues[2].key == "PROJ-300"

    def test_sort_comprehensive(self):
        """Complete sort test with all criteria."""
        issues = [
            MockIssue("PROJ-5", "Done", "Critical"),
            MockIssue("PROJ-2", "To Do", "Low"),
            MockIssue("PROJ-4", "In Progress", "High"),
            MockIssue("PROJ-1", "To Do", "Critical"),
            MockIssue("PROJ-3", "In Progress", "Medium"),
        ]

        sorter = IssueSorter()
        sorted_issues = sorter.sort(issues)

        # Expected order:
        # 1. PROJ-1 (To Do, Critical)
        # 2. PROJ-2 (To Do, Low)
        # 3. PROJ-4 (In Progress, High)
        # 4. PROJ-3 (In Progress, Medium)
        # 5. PROJ-5 (Done, Critical)
        assert sorted_issues[0].key == "PROJ-1"
        assert sorted_issues[1].key == "PROJ-2"
        assert sorted_issues[2].key == "PROJ-4"
        assert sorted_issues[3].key == "PROJ-3"
        assert sorted_issues[4].key == "PROJ-5"

    def test_case_insensitive_status(self):
        """Status matching should be case-insensitive."""
        issues = [
            MockIssue("PROJ-1", "DONE", "High"),
            MockIssue("PROJ-2", "To Do", "High"),
            MockIssue("PROJ-3", "in progress", "High"),
        ]

        sorter = IssueSorter()
        sorted_issues = sorter.sort(issues)

        assert sorted_issues[0].key == "PROJ-2"  # To Do
        assert sorted_issues[1].key == "PROJ-3"  # In Progress
        assert sorted_issues[2].key == "PROJ-1"  # Done

    def test_case_insensitive_priority(self):
        """Priority matching should be case-insensitive."""
        issues = [
            MockIssue("PROJ-1", "To Do", "LOW"),
            MockIssue("PROJ-2", "To Do", "Critical"),
            MockIssue("PROJ-3", "To Do", "HIGH"),
        ]

        sorter = IssueSorter()
        sorted_issues = sorter.sort(issues)

        assert sorted_issues[0].key == "PROJ-2"  # Critical
        assert sorted_issues[1].key == "PROJ-3"  # High
        assert sorted_issues[2].key == "PROJ-1"  # Low

    def test_unknown_status_goes_to_end(self):
        """Unknown status should be placed at the end."""
        issues = [
            MockIssue("PROJ-1", "Unknown Status", "High"),
            MockIssue("PROJ-2", "To Do", "High"),
        ]

        sorter = IssueSorter()
        sorted_issues = sorter.sort(issues)

        assert sorted_issues[0].key == "PROJ-2"  # Known status first
        assert sorted_issues[1].key == "PROJ-1"  # Unknown status last

    def test_unknown_priority_goes_to_end(self):
        """Unknown priority should be placed at the end."""
        issues = [
            MockIssue("PROJ-1", "To Do", "Unknown Priority"),
            MockIssue("PROJ-2", "To Do", "High"),
        ]

        sorter = IssueSorter()
        sorted_issues = sorter.sort(issues)

        assert sorted_issues[0].key == "PROJ-2"  # Known priority first
        assert sorted_issues[1].key == "PROJ-1"  # Unknown priority last

    def test_empty_list(self):
        """Sorting empty list should return empty list."""
        sorter = IssueSorter()
        sorted_issues = sorter.sort([])

        assert sorted_issues == []

    def test_single_issue(self):
        """Sorting single issue should return same issue."""
        issues = [MockIssue("PROJ-1", "To Do", "High")]

        sorter = IssueSorter()
        sorted_issues = sorter.sort(issues)

        assert len(sorted_issues) == 1
        assert sorted_issues[0].key == "PROJ-1"

    def test_get_sort_description(self):
        """Should return human-readable description."""
        sorter = IssueSorter()
        description = sorter.get_sort_description()

        assert description == "Status → Priority → Key"

    def test_custom_config(self):
        """Should accept custom configuration."""
        custom_config = IssueSortConfig(
            status_order={"custom": 0, "status": 1},
            priority_order={"p1": 0, "p2": 1}
        )

        issues = [
            MockIssue("PROJ-2", "status", "p1"),
            MockIssue("PROJ-1", "custom", "p2"),
        ]

        sorter = IssueSorter(config=custom_config)
        sorted_issues = sorter.sort(issues)

        assert sorted_issues[0].key == "PROJ-1"  # custom status comes first
        assert sorted_issues[1].key == "PROJ-2"
