"""Tests for grind.router module."""

import pytest

from grind.router import CostAwareRouter


class TestCostAwareRouter:
    """Test suite for CostAwareRouter task classification."""

    @pytest.fixture
    def router(self):
        """Create a router instance for tests."""
        return CostAwareRouter()

    # Simple task tests
    def test_route_typo_fix(self, router):
        """Test that typo fixes are routed to haiku."""
        assert router.route_task("fix typo in README") == "haiku"
        assert router.route_task("Fix Typo in documentation") == "haiku"
        assert router.route_task("correct spelling error") == "haiku"

    def test_route_formatting(self, router):
        """Test that formatting changes are routed to haiku."""
        assert router.route_task("format the code") == "haiku"
        assert router.route_task("fix formatting in main.py") == "haiku"
        assert router.route_task("adjust indentation") == "haiku"
        assert router.route_task("fix indent issues") == "haiku"
        assert router.route_task("remove extra whitespace") == "haiku"

    def test_route_comments(self, router):
        """Test that comment additions are routed to haiku."""
        assert router.route_task("add comment to function") == "haiku"
        assert router.route_task("add docstring comment") == "haiku"
        assert router.route_task("update comment explaining logic") == "haiku"

    def test_route_simple_renames(self, router):
        """Test that simple rename operations are routed to haiku."""
        assert router.route_task("rename variable foo to bar") == "haiku"
        assert router.route_task("rename file config.py") == "haiku"

    def test_route_deletions(self, router):
        """Test that deletion operations are routed to haiku."""
        assert router.route_task("delete unused function") == "haiku"
        assert router.route_task("remove old code") == "haiku"
        assert router.route_task("remove deprecated method") == "haiku"

    def test_route_version_bumps(self, router):
        """Test that version updates are routed to haiku."""
        assert router.route_task("update version to 1.2.3") == "haiku"
        assert router.route_task("bump version number") == "haiku"

    def test_route_simple_fixes(self, router):
        """Test that simple fixes are routed to haiku."""
        assert router.route_task("simple fix for import") == "haiku"
        assert router.route_task("quick simple fix") == "haiku"

    # Complex task tests
    def test_route_architecture_changes(self, router):
        """Test that architecture changes are routed to opus."""
        assert router.route_task("redesign the architecture") == "opus"
        assert router.route_task("refactor system to use event-driven model") == "opus"
        assert router.route_task("redesign data layer") == "opus"

    def test_route_migrations(self, router):
        """Test that migration tasks are routed to opus."""
        assert router.route_task("migrate to new database") == "opus"
        assert router.route_task("handle migration from SQLite to PostgreSQL") == "opus"
        assert router.route_task("migrate authentication to OAuth2") == "opus"

    def test_route_authentication(self, router):
        """Test that authentication implementations are routed to opus."""
        assert router.route_task("implement authentication system") == "opus"
        assert router.route_task("implement authentication layer") == "opus"
        assert router.route_task("implement authorization for users") == "opus"

    def test_route_database_features(self, router):
        """Test that database additions are routed to opus."""
        assert router.route_task("add database connection pooling") == "opus"
        assert router.route_task("add database backend") == "opus"

    def test_route_new_features(self, router):
        """Test that new features are routed to opus."""
        assert router.route_task("add new feature for user management") == "opus"
        assert router.route_task("implement complex feature") == "opus"

    def test_route_optimization(self, router):
        """Test that optimization tasks are routed to opus."""
        assert router.route_task("optimize query performance") == "opus"
        assert router.route_task("performance tuning for API") == "opus"

    def test_route_security(self, router):
        """Test that security implementations are routed to opus."""
        assert router.route_task("implement security headers") == "opus"
        assert router.route_task("add security layer for authentication") == "opus"

    def test_route_scalability(self, router):
        """Test that scalability features are routed to opus."""
        assert router.route_task("scale the application to handle more traffic") == "opus"
        assert router.route_task("implement distributed caching") == "opus"
        assert router.route_task("add microservice for payments") == "opus"

    # Medium task tests (default behavior)
    def test_route_api_endpoint(self, router):
        """Test that standard API endpoints are routed to sonnet."""
        assert router.route_task("add new API endpoint") == "sonnet"
        assert router.route_task("create REST endpoint for users") == "sonnet"

    def test_route_bug_fixes(self, router):
        """Test that moderate bug fixes are routed to sonnet."""
        assert router.route_task("fix bug in user login") == "sonnet"
        assert router.route_task("resolve issue with payment processing") == "sonnet"

    def test_route_standard_features(self, router):
        """Test that standard features are routed to sonnet."""
        assert router.route_task("add pagination to list view") == "sonnet"
        assert router.route_task("implement search functionality") == "sonnet"
        assert router.route_task("add validation to form") == "sonnet"

    def test_route_refactoring(self, router):
        """Test that moderate refactoring is routed to sonnet."""
        assert router.route_task("refactor the helper functions") == "sonnet"
        assert router.route_task("clean up code in module") == "sonnet"

    def test_route_tests(self, router):
        """Test that test writing is routed to sonnet."""
        assert router.route_task("write unit tests for service") == "sonnet"
        assert router.route_task("add integration tests") == "sonnet"

    def test_route_documentation(self, router):
        """Test that documentation tasks are routed to sonnet."""
        assert router.route_task("write API documentation") == "sonnet"
        assert router.route_task("update developer guide") == "sonnet"

    # Edge cases and special scenarios
    def test_route_empty_string(self, router):
        """Test that empty strings default to sonnet."""
        assert router.route_task("") == "sonnet"

    def test_route_case_insensitive(self, router):
        """Test that routing is case-insensitive."""
        assert router.route_task("FIX TYPO IN FILE") == "haiku"
        assert router.route_task("MIGRATE DATABASE") == "opus"
        assert router.route_task("Add API Endpoint") == "sonnet"

    def test_route_with_extra_whitespace(self, router):
        """Test that extra whitespace is handled correctly."""
        assert router.route_task("  fix typo  ") == "haiku"
        assert router.route_task("  migrate system  ") == "opus"
        assert router.route_task("  add feature  ") == "sonnet"

    def test_route_combined_keywords(self, router):
        """Test behavior with multiple keyword matches."""
        # Simple keyword should match first
        assert router.route_task("fix typo and update architecture") == "haiku"
        # Complex keyword should match if no simple match
        assert router.route_task("add new feature with migration") == "opus"

    def test_route_partial_keyword_matches(self, router):
        """Test that keywords must be substrings."""
        # These should match because keywords are substrings
        assert router.route_task("fixing typos in multiple files") == "haiku"
        assert router.route_task("system migration plan") == "opus"
        # These should not match and default to sonnet
        assert router.route_task("typical development task") == "sonnet"
        assert router.route_task("regular coding work") == "sonnet"

    def test_route_various_medium_tasks(self, router):
        """Test various tasks that should default to medium complexity."""
        assert router.route_task("create helper function") == "sonnet"
        assert router.route_task("update method signature") == "sonnet"
        assert router.route_task("fix edge case in parser") == "sonnet"
        assert router.route_task("improve error messages") == "sonnet"
        assert router.route_task("add logging statements") == "sonnet"


class TestCostAwareRouterInitialization:
    """Test router initialization and keyword configuration."""

    def test_router_has_simple_keywords(self):
        """Test that router initializes with simple keywords."""
        router = CostAwareRouter()
        assert isinstance(router.simple_keywords, list)
        assert len(router.simple_keywords) > 0
        assert "typo" in router.simple_keywords

    def test_router_has_complex_keywords(self):
        """Test that router initializes with complex keywords."""
        router = CostAwareRouter()
        assert isinstance(router.complex_keywords, list)
        assert len(router.complex_keywords) > 0
        assert "architecture" in router.complex_keywords

    def test_keyword_lists_are_distinct(self):
        """Test that simple and complex keyword lists don't overlap."""
        router = CostAwareRouter()
        simple_set = set(router.simple_keywords)
        complex_set = set(router.complex_keywords)
        assert len(simple_set.intersection(complex_set)) == 0
