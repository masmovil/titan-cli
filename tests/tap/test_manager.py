"""
Tests for TAP Manager (TAPManager).

Tests AdapterManager with complete workflow integration.
"""

from __future__ import annotations

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

from titan_cli.tap.manager import AdapterManager
from titan_cli.tap.registry import AdapterRegistry


# Mock adapter for testing
class MockAdapter:
    """Mock adapter for testing."""

    def __init__(self, **kwargs):
        """Initialize with any config params."""
        self.config = kwargs

    @staticmethod
    def convert_tool(titan_tool):
        return {"name": titan_tool.name}

    @staticmethod
    def convert_tools(titan_tools):
        return [MockAdapter.convert_tool(t) for t in titan_tools]

    @staticmethod
    def execute_tool(tool_name, tool_input, tools):
        return f"executed: {tool_name}"


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset registry before each test."""
    AdapterRegistry.reset()
    yield
    AdapterRegistry.reset()


@pytest.fixture
def manager():
    """Create a manager without auto-discovery."""
    return AdapterManager(auto_discover=False)


@pytest.fixture
def temp_config_dir():
    """Create temporary directory for config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestManagerInitialization:
    """Tests for manager initialization."""

    def test_init_default(self):
        """Test default initialization."""
        with patch.object(AdapterManager, '_auto_discover_builtin'):
            manager = AdapterManager()

        assert manager.registry is not None
        assert manager.loader is not None
        assert manager.factory is not None

    def test_init_without_auto_discover(self):
        """Test initialization without auto-discovery."""
        manager = AdapterManager(auto_discover=False)

        assert manager.registry is not None
        assert manager.loader is not None
        assert manager.factory is not None

    def test_init_with_custom_registry(self):
        """Test initialization with custom registry."""
        custom_registry = AdapterRegistry.get_instance()
        manager = AdapterManager(registry=custom_registry, auto_discover=False)

        assert manager.registry is custom_registry

    def test_auto_discover_runs_on_init(self):
        """Test that auto-discovery runs by default."""
        with patch.object(AdapterManager, '_auto_discover_builtin') as mock_discover:
            AdapterManager()
            mock_discover.assert_called_once()

    def test_auto_discover_not_run_when_disabled(self):
        """Test that auto-discovery can be disabled."""
        with patch.object(AdapterManager, '_auto_discover_builtin') as mock_discover:
            AdapterManager(auto_discover=False)
            mock_discover.assert_not_called()


class TestFromConfig:
    """Tests for from_config class method."""

    def test_from_config_yaml(self, temp_config_dir):
        """Test creating manager from YAML config."""
        config = {"adapters": [{"name": "test", "module": "module.Test"}]}

        try:
            import yaml
            config_file = temp_config_dir / "adapters.yml"
            with open(config_file, 'w') as f:
                yaml.dump(config, f)

            manager = AdapterManager.from_config(config_file, auto_discover=False)

            assert isinstance(manager, AdapterManager)
            assert manager.registry.is_registered("test")
        except ImportError:
            pytest.skip("PyYAML not installed")

    def test_from_config_json(self, temp_config_dir):
        """Test creating manager from JSON config."""
        config = {"adapters": [{"name": "test", "module": "module.Test"}]}

        config_file = temp_config_dir / "adapters.json"
        with open(config_file, 'w') as f:
            json.dump(config, f)

        manager = AdapterManager.from_config(config_file, auto_discover=False)

        assert isinstance(manager, AdapterManager)
        assert manager.registry.is_registered("test")


class TestLoadConfig:
    """Tests for load_config method."""

    def test_load_config_json(self, manager, temp_config_dir):
        """Test loading JSON configuration."""
        config = {"adapters": [
            {"name": "json_adapter", "module": "module.JSONAdapter"}
        ]}

        config_file = temp_config_dir / "adapters.json"
        with open(config_file, 'w') as f:
            json.dump(config, f)

        loaded = manager.load_config(config_file)

        assert loaded == 1
        assert manager.is_available("json_adapter")

    def test_load_config_unsupported_format(self, manager, temp_config_dir):
        """Test that unsupported format raises error."""
        config_file = temp_config_dir / "adapters.txt"
        config_file.write_text("unsupported")

        with pytest.raises(ValueError, match="Unsupported config format"):
            manager.load_config(config_file)


class TestGetAdapter:
    """Tests for get method."""

    def test_get_registered_adapter(self, manager):
        """Test getting a registered adapter."""
        manager.registry.register("test", MockAdapter)

        adapter = manager.get("test")

        assert isinstance(adapter, MockAdapter)

    def test_get_lazy_loaded_adapter(self, manager):
        """Test getting a lazy-loaded adapter."""
        manager.registry.register_lazy(
            "lazy_test",
            "tests.tap.test_manager.MockAdapter"
        )

        adapter = manager.get("lazy_test")

        assert isinstance(adapter, MockAdapter)

    def test_get_nonexistent_adapter(self, manager):
        """Test getting non-existent adapter raises error."""
        with pytest.raises(KeyError, match="not found"):
            manager.get("nonexistent")

    def test_get_with_cache_control(self, manager):
        """Test controlling cache behavior."""
        manager.registry.register("test", MockAdapter)

        adapter1 = manager.get("test", use_cache=True)
        adapter2 = manager.get("test", use_cache=True)

        # Should be same instance (cached)
        assert adapter1 is adapter2


class TestGetWithFallback:
    """Tests for get_with_fallback method."""

    def test_fallback_first_succeeds(self, manager):
        """Test fallback when first adapter succeeds."""
        manager.registry.register("first", MockAdapter)
        manager.registry.register("second", MockAdapter)

        name, adapter = manager.get_with_fallback(["first", "second"])

        assert name == "first"
        assert adapter is not None

    def test_fallback_second_succeeds(self, manager):
        """Test fallback when first fails."""
        manager.registry.register("second", MockAdapter)

        name, adapter = manager.get_with_fallback(["nonexistent", "second"])

        assert name == "second"
        assert adapter is not None

    def test_fallback_all_fail(self, manager):
        """Test fallback when all adapters fail."""
        with pytest.raises(RuntimeError, match="Failed to create adapter"):
            manager.get_with_fallback(["none1", "none2", "none3"])


class TestListAndQuery:
    """Tests for list and query methods."""

    def test_list_adapters_empty(self, manager):
        """Test listing adapters when none registered."""
        adapters = manager.list_adapters()

        assert adapters == []

    def test_list_adapters_multiple(self, manager):
        """Test listing multiple adapters."""
        manager.registry.register("adapter1", MockAdapter)
        manager.registry.register("adapter2", MockAdapter)
        manager.registry.register_lazy("adapter3", "module.path")

        adapters = manager.list_adapters()

        assert len(adapters) == 3
        assert "adapter1" in adapters
        assert "adapter2" in adapters
        assert "adapter3" in adapters

    def test_is_available_true(self, manager):
        """Test is_available returns True for registered adapter."""
        manager.registry.register("test", MockAdapter)

        assert manager.is_available("test") is True

    def test_is_available_false(self, manager):
        """Test is_available returns False for unregistered adapter."""
        assert manager.is_available("nonexistent") is False

    def test_get_metadata(self, manager):
        """Test getting adapter metadata."""
        metadata = {"version": "1.0.0", "provider": "Test"}
        manager.registry.register("test", MockAdapter, metadata=metadata)

        retrieved = manager.get_metadata("test")

        assert retrieved["version"] == "1.0.0"
        assert retrieved["provider"] == "Test"

    def test_get_metadata_nonexistent(self, manager):
        """Test getting metadata for non-existent adapter raises error."""
        with pytest.raises(KeyError):
            manager.get_metadata("nonexistent")


class TestReload:
    """Tests for reload methods."""

    def test_reload_lazy_adapter(self, manager):
        """Test reloading a lazy adapter."""
        manager.registry.register_lazy(
            "lazy_test",
            "tests.tap.test_manager.MockAdapter"
        )
        manager.get("lazy_test")  # Load and cache it

        manager.reload("lazy_test")

        # Should still be available and re-registered
        assert manager.is_available("lazy_test")

    def test_reload_clears_cache(self, manager):
        """Test that reload clears factory cache."""
        manager.registry.register_lazy(
            "test",
            "tests.tap.test_manager.MockAdapter"
        )

        # Get and cache
        adapter1 = manager.get("test", use_cache=True)

        # Reload
        manager.reload("test")

        # Get again - should still work
        adapter2 = manager.get("test", use_cache=True)

        assert adapter1 is not None
        assert adapter2 is not None

    def test_reload_all(self, manager):
        """Test reloading all adapters."""
        manager.registry.register_lazy("adapter1", "tests.tap.test_manager.MockAdapter")
        manager.registry.register_lazy("adapter2", "tests.tap.test_manager.MockAdapter")

        manager.reload_all()

        # All should still be available after reload
        assert manager.is_available("adapter1")
        assert manager.is_available("adapter2")


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_complete_workflow(self, temp_config_dir):
        """Test complete manager workflow."""
        # 1. Create manager
        manager = AdapterManager(auto_discover=False)

        # 2. Load configuration
        config = {
            "adapters": [
                {"name": "test1", "module": "tests.tap.test_manager.MockAdapter"},
                {"name": "test2", "module": "tests.tap.test_manager.MockAdapter"}
            ]
        }
        config_file = temp_config_dir / "adapters.json"
        with open(config_file, 'w') as f:
            json.dump(config, f)

        loaded = manager.load_config(config_file)
        assert loaded == 2

        # 3. List adapters
        adapters = manager.list_adapters()
        assert len(adapters) == 2

        # 4. Get adapter
        adapter = manager.get("test1")
        assert isinstance(adapter, MockAdapter)

        # 5. Check availability
        assert manager.is_available("test1")
        assert manager.is_available("test2")

        # 6. Get metadata
        metadata = manager.get_metadata("test1")
        assert isinstance(metadata, dict)

        # 7. Reload
        manager.reload("test1")
        assert manager.is_available("test1")

        # 8. Get again after reload
        adapter_after = manager.get("test1")
        assert isinstance(adapter_after, MockAdapter)

    def test_fallback_strategy_workflow(self, manager):
        """Test fallback strategy in real scenario."""
        # Register adapters with different priorities
        manager.registry.register("primary", MockAdapter)
        manager.registry.register("secondary", MockAdapter)
        manager.registry.register("tertiary", MockAdapter)

        # Try fallback
        name, adapter = manager.get_with_fallback([
            "primary",
            "secondary",
            "tertiary"
        ])

        assert name == "primary"
        assert adapter is not None


class TestBuiltinAdapters:
    """Tests for built-in adapter discovery."""

    def test_auto_discover_finds_anthropic(self):
        """Test that auto-discovery finds Anthropic adapter."""
        manager = AdapterManager()  # auto_discover=True by default

        # Check if anthropic was registered
        assert manager.is_available("anthropic")

    def test_auto_discover_finds_openai(self):
        """Test that auto-discovery finds OpenAI adapter."""
        manager = AdapterManager()

        # Check if openai was registered
        assert manager.is_available("openai")

    def test_can_get_anthropic_adapter(self):
        """Test that we can get Anthropic adapter."""
        manager = AdapterManager()

        adapter = manager.get("anthropic")
        assert adapter is not None
        assert hasattr(adapter, 'convert_tool')
        assert hasattr(adapter, 'convert_tools')
        assert hasattr(adapter, 'execute_tool')

    def test_can_get_openai_adapter(self):
        """Test that we can get OpenAI adapter."""
        manager = AdapterManager()

        adapter = manager.get("openai")
        assert adapter is not None
        assert hasattr(adapter, 'convert_tool')
        assert hasattr(adapter, 'convert_tools')
        assert hasattr(adapter, 'execute_tool')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
