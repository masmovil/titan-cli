# Plugins

Titan exposes plugin capabilities through three public layers:

- `Client API`: Python entry points used from Titan code.
- `Workflow Steps`: reusable step functions exposed through `plugin.get_steps()`.
- `Built-in Workflows`: YAML workflows shipped by each plugin.

This section documents official plugins from those three angles so users can both call
plugin clients directly and compose workflows from reusable public steps.

## Official plugins

Titan ships with five official plugins:

| Plugin | Description |
|--------|-------------|
| **git** | Smart commits, branch management, AI-powered commit messages |
| **github** | Create PRs with AI descriptions, manage issues, code reviews |
| **jira** | Search issues, AI-powered analysis, workflow automation |
| **slack** | Personal Slack auth, workspace summaries, and reusable Slack workflow steps |
| **docker** | Docker Compose lifecycle management and image build/push workflows |

Enable them per project in `.titan/config.toml`:

```toml
[plugins.git]
enabled = true

[plugins.github]
enabled = true

[plugins.jira]
enabled = true

[plugins.slack]
enabled = true

[plugins.docker]
enabled = true
```

For each plugin, the docs are split into:

- `Overview`: requirements, configuration, and entry points.
- `Client API`: public client methods grouped by domain.
- `Workflow Steps`: public reusable steps grouped by functionality.
- `Built-in Workflows`: workflows shipped by the plugin and how to extend them.

## Community plugins

Titan also supports community plugins from external repositories.

There are currently two source channels:

- `stable`: pin a plugin version in the project config using a git tag or commit.
- `dev_local`: use a local checkout of a plugin repository during development.

The shared stable pin lives in `.titan/config.toml`:

```toml
[plugins.custom]
enabled = true

[plugins.custom.source]
channel = "stable"
repo_url = "https://github.com/user/titan-plugin-custom"
requested_ref = "v1.2.0"
resolved_commit = "0123456789abcdef0123456789abcdef01234567"
```

`requested_ref` stores the exact tag or ref used by that repository. Some repos use
tags like `v1.2.0`; others use `1.2.0`.

For local plugin development, the active override lives in `~/.titan/config.toml`:

```toml
[plugins.custom.source]
channel = "dev_local"
path = "/absolute/path/to/local/plugin/repo"
```

In `dev_local`, Titan loads the plugin directly from the local repository. In `stable`,
Titan prepares an isolated local runtime for the pinned commit.

## Version compatibility

A plugin is built against the Titan plugin API of a specific titan-cli range. When the
two drift apart — a project pinned to an old plugin version after upgrading titan-cli,
or updating a plugin beyond what the installed titan-cli supports — the plugin cannot
load. Titan detects this in both directions:

- **Declared contract.** The plugin's `pyproject.toml` dependency on `titan-cli` is the
  compatibility contract. Titan checks it before loading a plugin, before installing
  one, and before applying an update — an update whose target version requires a
  different titan-cli is rejected with a message telling you which side to upgrade,
  instead of leaving a broken pin.
- **Fallback detection.** If a plugin with loose bounds imports a `titan_cli.*` module
  that does not exist in the running titan-cli, the failure is reported as a version
  incompatibility ("update the plugin"), not as a generic crash.

An incompatible or crashed plugin appears as **Load failed** in Plugin Management, with
the reason in the details panel. A failed plugin with a stable pin can still be updated
from there (the pin lives in the project config, not in the plugin), so a broken pinned
version is never a dead end.

**For plugin authors:**

- Declare an accurate `titan-cli` bound and keep it honest, e.g.
  `titan-cli = ">=0.8.0,<0.9"`. A bound like `>=0.6.0` promises compatibility with
  every future titan-cli, which no plugin can keep; without a real upper bound only
  the fallback detection protects your users.
- When migrating to a renamed or moved titan-cli API, prefer a release that supports
  **both** APIs (`try: import new / except ImportError: import old`) so projects can
  upgrade titan-cli and the plugin in either order. Drop the shim, and raise the lower
  bound, one release later.
- Bump your plugin's MAJOR (or clearly flag the release) when a version stops
  supporting a titan-cli range that the previous release supported.
