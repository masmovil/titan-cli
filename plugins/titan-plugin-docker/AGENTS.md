# AGENTS.md - Titan Docker Plugin

Documentation for AI coding agents working on the `titan-plugin-docker`.

---

## Plugin Overview

**Titan Docker Plugin** provides Docker Compose lifecycle management and image
build/push workflows for Titan CLI, following the same 5-layer architecture as
`titan-plugin-git` (Steps → Operations → Client → Services → Network).

Scope:

- Compose lifecycle: `up` / `down` / `status`, operating on an arbitrary list
  of service names, an "all services" default, or a project-configured named
  `service_groups` entry (open dictionary, no reserved names).
- Image builds: `docker buildx build` (single or multi-platform) with
  optional push, per `build_targets` entry configured in
  `.titan/config.toml`.

The plugin is intentionally generic: it has no notion of any specific
project's services or images. `service_groups` and `build_targets` are pure
project configuration (`DockerPluginConfig` in
`titan_cli/core/plugins/models.py`).

---

## Project Structure

```text
titan_plugin_docker/
├── __init__.py
├── plugin.py
├── exceptions.py
├── clients/
│   ├── docker_client.py
│   ├── network/
│   │   └── docker_network.py
│   └── services/
│       ├── compose_service.py
│       └── build_service.py
├── models/
│   ├── network/
│   ├── view/
│   └── mappers/
├── operations/
│   ├── compose_operations.py
│   └── build_operations.py
├── steps/
└── workflows/
```

---

## Working Rules

- No `messages.py` / message-constant class — write user-facing strings
  directly at their call site.
- No doctest examples in docstrings — tests live under `tests/`.
- Steps never call `subprocess`/`DockerNetwork` directly; they go through
  `ctx.docker` (the `DockerClient` facade) and the `operations/` layer.
- Don't hardcode project-specific service or image names anywhere in this
  package — those always come from `DockerPluginConfig`.
