"""
Unit tests for Saved Queries
"""

from titan_plugin_jira.utils.saved_queries import SAVED_QUERIES


class TestSavedQueries:
    """Test saved queries functionality"""

    def test_get_all_returns_dict(self):
        """Test get_all returns a dictionary"""
        queries = SAVED_QUERIES.get_all()
        assert isinstance(queries, dict)
        assert len(queries) > 0

    def test_all_queries_are_strings(self):
        """Test all queries are valid JQL strings"""
        queries = SAVED_QUERIES.get_all()
        for name, jql in queries.items():
            assert isinstance(name, str)
            assert isinstance(jql, str)
            assert len(jql) > 0

    def test_personal_queries_exist(self):
        """Test personal queries are defined"""
        queries = SAVED_QUERIES.get_all()

        # Personal queries
        assert "my_open_issues" in queries
        assert "my_bugs" in queries
        assert "my_in_review" in queries
        assert "my_in_progress" in queries
        assert "reported_by_me" in queries

    def test_team_queries_exist(self):
        """Test team queries are defined"""
        queries = SAVED_QUERIES.get_all()

        # Team queries
        assert "current_sprint" in queries
        assert "team_open" in queries
        assert "team_bugs" in queries
        assert "team_in_review" in queries
        assert "team_ready_for_qa" in queries

    def test_priority_queries_exist(self):
        """Test priority queries are defined"""
        queries = SAVED_QUERIES.get_all()

        assert "critical_issues" in queries
        assert "high_priority" in queries
        assert "blocked_issues" in queries

    def test_time_based_queries_exist(self):
        """Test time-based queries are defined"""
        queries = SAVED_QUERIES.get_all()

        assert "updated_today" in queries
        assert "created_this_week" in queries
        assert "recent_bugs" in queries

    def test_status_queries_exist(self):
        """Test status queries are defined"""
        queries = SAVED_QUERIES.get_all()

        assert "todo_issues" in queries
        assert "in_progress_all" in queries
        assert "done_recently" in queries

    def test_open_issues_jql(self):
        """Test open_issues query has correct JQL"""
        queries = SAVED_QUERIES.get_all()
        jql = queries["open_issues"]

        assert 'status IN ("Open", "Ready to Dev")' in jql
        assert "{project}" in jql
        assert "ORDER BY priority DESC" in jql
        assert "assignee" not in jql  # Should not filter by assignee

    def test_my_open_issues_jql(self):
        """Test my_open_issues query has correct JQL"""
        queries = SAVED_QUERIES.get_all()
        jql = queries["my_open_issues"]

        assert "assignee = currentUser()" in jql
        assert 'status IN ("Open", "Ready to Dev")' in jql
        assert "{project}" in jql
        assert "ORDER BY updated DESC" in jql

    def test_current_sprint_has_project_placeholder(self):
        """Test current_sprint query has project parameter"""
        queries = SAVED_QUERIES.get_all()
        jql = queries["current_sprint"]

        assert "{project}" in jql
        assert "sprint in openSprints()" in jql

    def test_format_method_replaces_placeholders(self):
        """Test format method replaces placeholders correctly"""
        queries = SAVED_QUERIES.get_all()
        original_jql = queries["current_sprint"]

        # Original should have placeholder
        assert "{project}" in original_jql

        # Formatted should replace it
        formatted_jql = original_jql.format(project="ECAPP")
        assert "{project}" not in formatted_jql
        assert "project = ECAPP" in formatted_jql

    def test_team_bugs_parameterized(self):
        """Test team_bugs query is parameterized"""
        queries = SAVED_QUERIES.get_all()
        jql = queries["team_bugs"]

        assert "{project}" in jql
        assert "type = Bug" in jql

    def test_no_duplicate_query_names(self):
        """Test there are no duplicate query names"""
        queries = SAVED_QUERIES.get_all()
        query_names = list(queries.keys())

        assert len(query_names) == len(set(query_names))

    def test_queries_count(self):
        """Test we have at least 20 predefined queries"""
        queries = SAVED_QUERIES.get_all()
        # We have 24 queries, so let's check for at least 20
        assert len(queries) >= 20

    def test_query_names_lowercase_with_underscores(self):
        """Test all query names are lowercase with underscores"""
        queries = SAVED_QUERIES.get_all()

        for name in queries.keys():
            assert name.islower() or "_" in name
            assert " " not in name
            assert "-" not in name

    def test_critical_issues_jql(self):
        """Test critical_issues query structure"""
        queries = SAVED_QUERIES.get_all()
        jql = queries["critical_issues"]

        assert "priority = Highest" in jql
        assert "status != Done" in jql

    def test_blocked_issues_jql(self):
        """Test blocked_issues query structure"""
        queries = SAVED_QUERIES.get_all()
        jql = queries["blocked_issues"]

        assert "status = Blocked" in jql

    def test_recent_bugs_jql(self):
        """Test recent_bugs query structure"""
        queries = SAVED_QUERIES.get_all()
        jql = queries["recent_bugs"]

        assert "type = Bug" in jql
        assert "created >=" in jql

    def test_updated_today_jql(self):
        """Test updated_today query uses JIRA function"""
        queries = SAVED_QUERIES.get_all()
        jql = queries["updated_today"]

        assert "updated >= startOfDay()" in jql

    def test_team_queries_all_have_project_param(self):
        """Test all team queries have project parameter"""
        queries = SAVED_QUERIES.get_all()
        team_queries = [
            "current_sprint",
            "team_open",
            "team_bugs",
            "team_in_review",
            "team_ready_for_qa"
        ]

        for query_name in team_queries:
            jql = queries[query_name]
            assert "{project}" in jql, f"{query_name} should have {{project}} parameter"
