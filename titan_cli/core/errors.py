"""
Custom Exception Types for Titan CLI
"""
from ..messages import msg

class TitanError(Exception):
    """Base exception for all application-specific errors."""
    pass

class PluginError(TitanError):
    """Base exception for plugin-related errors."""
    pass

class PluginLoadError(PluginError):
    """Raised when a plugin fails to load from an entry point."""
    def __init__(self, plugin_name: str, original_exception: Exception):
        self.plugin_name = plugin_name
        self.original_exception = original_exception
        # Do not call super().__init__ with message here, as it's formatted by __str__

    def __str__(self) -> str:
        return msg.Errors.PLUGIN_LOAD_FAILED.format(
            plugin_name=self.plugin_name, 
            error=str(self.original_exception)
        )

class PluginInitializationError(PluginError):
    """Raised when a plugin fails to initialize."""

    def __init__(self, plugin_name: str, original_exception: Exception):
        self.plugin_name = plugin_name
        self.original_exception = original_exception
        # Do not call super().__init__ with message here, as it's formatted by __str__

    def __str__(self) -> str:
        return msg.Errors.PLUGIN_INIT_FAILED.format(
            plugin_name=self.plugin_name,
            error=str(self.original_exception)
        )

class ConfigError(TitanError):
    """Base exception for configuration-related errors."""
    pass

class ConfigNotFoundError(ConfigError, FileNotFoundError):
    """Raised when a config file cannot be found."""
    pass

class ConfigParseError(ConfigError):

    """Raised when a config file cannot be parsed."""

    def __init__(self, file_path: str, original_exception: Exception):

        self.file_path = file_path
        self.original_exception = original_exception

        message = msg.Errors.CONFIG_PARSE_ERROR.format(
            file_path=file_path,
            error=original_exception
        )

        super().__init__(message)



class ConfigWriteError(ConfigError):

    """Raised when writing to a configuration file fails."""

    def __init__(self, file_path: str, original_exception: Exception):

        self.file_path = file_path
        self.original_exception = original_exception

        message = msg.Errors.CONFIG_WRITE_FAILED.format(
            path=file_path,
            error=original_exception
        )

        super().__init__(message)
