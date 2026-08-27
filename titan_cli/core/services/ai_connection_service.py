"""Application service for Titan AI connection management."""

from titan_cli.core.config import TitanConfig


class AIConnectionService:
    """Manage AI connection configuration for CLI and native clients."""

    def __init__(self, config: TitanConfig) -> None:
        self._config = config

    def list_connections(self) -> dict[str, object]:
        """Return configured AI connections in a stable native-client shape."""
        return self._connections_payload()

    def upsert_connection(
        self,
        connection_id: str,
        connection_data: dict[str, object],
        *,
        api_key: str | None = None,
    ) -> dict[str, object]:
        """Create or update an AI connection and optionally store its secret."""
        self._config.upsert_ai_connection(connection_id, connection_data)

        if api_key:
            self._config.secrets.set(
                f"{connection_id}_api_key",
                api_key,
                scope="user",
            )

        return self._connections_payload()

    def set_default_connection(self, connection_id: str) -> dict[str, object]:
        """Set the default AI connection used by Titan workflows."""
        self._config.set_default_ai_connection(connection_id)
        return self._connections_payload()

    def list_models(self, connection_id: str) -> dict[str, object]:
        """Return available or suggested models for an AI connection."""
        ai_config = self._config.config.ai
        if not ai_config or connection_id not in ai_config.connections:
            raise ValueError(f"AI connection '{connection_id}' not found.")

        connection = ai_config.connections[connection_id]
        connection_type = getattr(
            connection.connection_type,
            "value",
            connection.connection_type,
        )

        if connection_type == "gateway":
            items = self._gateway_models(connection_id, connection)
        else:
            provider = getattr(connection.provider, "value", connection.provider)
            items = self._popular_direct_models(provider)

        return {
            "connection_id": connection_id,
            "default_model": connection.default_model,
            "items": items,
        }

    def _connections_payload(self) -> dict[str, object]:
        ai_config = self._config.get_ai_connections_config()
        default_connection = ai_config.get("default_connection")
        connections = []

        for connection_id, connection_data in sorted(
            ai_config.get("connections", {}).items()
        ):
            connections.append(
                {
                    "id": connection_id,
                    **connection_data,
                    "is_default": connection_id == default_connection,
                }
            )

        return {
            "default_connection": default_connection,
            "connections": connections,
        }

    def _gateway_models(self, connection_id: str, connection) -> list[dict[str, object]]:
        from titan_cli.ai.litellm_client import LiteLLMClient

        api_key = self._config.secrets.get(f"{connection_id}_api_key")
        models = LiteLLMClient(
            base_url=connection.base_url,
            api_key=api_key,
        ).list_models()
        return [
            {
                "id": model.id,
                "name": model.name,
                "owned_by": model.owned_by,
                "source": "gateway",
            }
            for model in models
        ]

    def _popular_direct_models(self, provider: str | None) -> list[dict[str, object]]:
        suggestions = {
            "anthropic": [
                "claude-sonnet-4-5",
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
            ],
            "openai": [
                "gpt-5",
                "gpt-5-mini",
                "gpt-4.1",
            ],
            "gemini": [
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-1.5-pro",
                "gemini-1.5-flash",
            ],
        }
        return [
            {"id": model, "name": model, "owned_by": provider, "source": "suggested"}
            for model in suggestions.get(provider or "", [])
        ]

