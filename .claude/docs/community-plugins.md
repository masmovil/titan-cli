# Community Plugins

## Overview

Titan supports community plugins in addition to the official plugins bundled with the CLI.

There are two source channels:

- `stable`: a shared project pin stored in `.titan/config.toml`
- `dev_local`: a user-local override stored in `~/.titan/config.toml`

Titan itself can remain globally installed, while project-pinned community plugins are prepared in isolated local runtimes.

---

## Key Files

| File | Role |
|------|------|
| `titan_cli/core/plugins/community_sources.py` | URL parsing, metadata preview, ref resolution, update checks |
| `titan_cli/core/plugins/runtime.py` | Isolated runtime/cache manager for `stable` community plugins |
| `titan_cli/core/plugins/models.py` | Plugin source config model |
| `titan_cli/core/plugins/plugin_registry.py` | Resolves effective source and loads `dev_local` or cached `stable` plugin code |
| `titan_cli/ui/tui/screens/install_plugin_screen.py` | Adds a stable community plugin to the current project |
| `titan_cli/ui/tui/screens/plugin_management.py` | Displays source state and handles update/remove/dev override actions |

---

## Source Model

### Shared project pin (`stable`)

The shared stable source lives in `.titan/config.toml`:

```toml
[plugins.custom]
enabled = true

[plugins.custom.source]
channel = "stable"
repo_url = "https://github.com/user/titan-plugin-custom"
requested_ref = "v1.2.0"
resolved_commit = "0123456789abcdef0123456789abcdef01234567"
```

Notes:
- `requested_ref` stores the exact tag/ref used by that repository
- `resolved_commit` is the operational truth
- this block is meant to be committed and reviewed in PRs

### User-local override (`dev_local`)

The active local development override lives in `~/.titan/config.toml`:

```toml
[plugins.custom.source]
channel = "dev_local"
path = "/absolute/path/to/local/plugin/repo"
```

Notes:
- this is not committed to the project
- if present, it wins over the project's `stable` pin on that machine
- when switching back to `stable`, the remembered `path` may stay in global config as UX state, but it is ignored

---

## Resolution Rules

Titan resolves the effective source in this order:

1. global `dev_local` override
2. project `stable` pin

If neither exists, the plugin is treated as a normal installed plugin with no community source metadata.

---

## Stable Install Flow

### 1. URL

The user enters a URL with an explicit ref:

```text
https://github.com/user/titan-plugin-custom@v1.2.0
https://github.com/user/titan-plugin-custom@abc123def456
```

Bare repository URLs without `@ref` are rejected.

### 2. Preview

Titan fetches `pyproject.toml` from that source and shows:
- package name
- version
- description
- authors
- Titan entry points
- Python dependencies

### 3. Pin + runtime

Titan resolves the requested ref to a full commit SHA and then:

1. writes the shared stable pin into the current project's `.titan/config.toml`
2. prepares an isolated runtime for that plugin commit
3. reloads config/registry so the plugin becomes available immediately

### 4. Done

The wizard shows the pinned ref/commit and the Titan plugin name if found.

---

## Runtime Layout

Stable community plugins are prepared in a cache like:

```text
~/.titan/plugin-cache/<plugin_name>/<resolved_commit>/
  src/
  venv/
```

The runtime manager:

1. checks out the pinned commit into `src/`
2. creates a dedicated `venv/`
3. installs the plugin into that isolated environment

The plugin registry then loads the plugin from:
- the cached source directory
- the cached `site-packages`

This gives dependency isolation per `plugin + commit` while still using the current in-process plugin API.

---

## Update Flow

Only `stable` community plugins can be updated. A plugin whose load failed can still be
updated: the pin lives in project config, not in the loaded plugin, and update is the
standard way out of a broken pinned version.

Update behavior:

1. check latest release/tag from the repo host
2. resolve that ref to a full SHA
3. compatibility gate: fetch the candidate's `pyproject.toml` at that SHA and check its
   declared `titan-cli` requirement against the running version — a positively-detected
   incompatibility aborts the update with an explanatory notify (fetch/parse failures do
   not block)
4. update the current project's `.titan/config.toml`
5. prepare the runtime for the new commit
6. reload Titan config/registry

`dev_local` has no update flow by design.

---

## Version Compatibility

The compatibility contract between a plugin and titan-cli is the plugin's declared
`titan-cli` dependency in its `pyproject.toml`.

- `parse_plugin_metadata` (community_sources.py) extracts it as `titan_requirement`
  (PEP 621 and Poetry layouts, including `^`/`~` translation).
- `get_titan_incompatibility(metadata, current_version)` returns a message or `None`.
  Absent/unparseable requirements never block.
- Enforced in three places: `_load_local_plugin` (plugin_registry.py, before import;
  raises `PluginIncompatibleError`), the install screen (blocking panel before writing
  the pin), and the update flow (step 3 above).
- Fallback heuristic: a `ModuleNotFoundError` for a `titan_cli.*` module during plugin
  import is re-raised as `PluginIncompatibleError` — a missing Titan API means the
  plugin was built for a different titan-cli, and the raw traceback misleads.
- UI: failed plugins show as "Load failed" (not "Not installed") in Plugin Management,
  with the error in the details panel and Update still available.

Contributor rule for breaking `titan_cli.*` changes (deprecation aliases, coordinated
plugin releases): see `docs/contributing/architecture.md`, "Plugin API Compatibility
Rule".

---

## Remove Flow

In Plugin Management:

- if the active source is `dev_local`, remove the local override from global config
- if the active source is `stable`, remove the plugin from the current project's config

This no longer uninstalls a package from Titan's global environment, because `stable` community plugins are no longer managed with `pipx inject`.

---

## Important Notes

- `~/.titan/community_plugins.toml` is no longer used
- `community.py` was replaced by `community_sources.py`
- official plugins can still follow their own global install path; the per-project runtime model here is specifically for community plugins

---

## Known Limits

- community plugins still run in-process after being imported
- dependency isolation is per plugin runtime, but execution is not sandboxed in a subprocess
- a future architecture could move plugin execution out-of-process if stronger isolation is needed
