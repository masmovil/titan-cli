# Architecture

!!! note "Coming soon"
    Detailed architecture documentation is being written. In the meantime, contributors can refer to the internal docs in `.claude/docs/` within the repository.

---

## Overview

Titan follows a 5-layer plugin architecture:

```
Steps → Operations → Client → Services → Network
  ↓         ↓          ↓         ↓          ↓
 UI    Business    Public   Data Access   HTTP/CLI
       Logic       API
```

Each official plugin (Git, GitHub, Jira) follows this structure. See the source in `plugins/` for reference implementations.

---

## Plugin API Compatibility Rule

Everything importable under `titan_cli.*` is de-facto public API for plugins: community
plugins run in-process and import Titan modules directly (`plugin_base`, `config`,
`security`, step/workflow helpers, ...). Moving, renaming, or deleting any of those
modules breaks every plugin release built against them — and the break only surfaces on
users' machines, when their pinned plugin stops loading after a titan-cli upgrade.

When a change removes or relocates something plugins import:

1. **Keep the old import path working for at least one minor release**, as a re-export
   or deprecated alias pointing at the new location. Delete it in the following minor.
2. **If a hard break is unavoidable**, coordinate releases with the known plugin repos
   before shipping: each plugin needs a release that supports both APIs (import
   fallback) or, at minimum, a release with the new API plus a corrected `titan-cli`
   lower bound — published so projects can update the moment they upgrade titan-cli.
3. **Never assume plugins will "just update"**: projects pin plugin versions by commit,
   so an old pin plus a new titan-cli is a combination that will exist in the wild.

Runtime enforcement (do not weaken it): the registry checks each plugin's declared
`titan-cli` requirement before importing it, translates `ModuleNotFoundError` on
`titan_cli.*` imports into a version-incompatibility error, and the install/update flows
refuse to pin a version whose requirement excludes the running titan-cli. Precedent:
`titan_cli.core.secrets` → `titan_cli.core.security` (0.8.0) shipped without an alias
and broke every pinned ragnarok plugin ≤ 0.10.0 on upgrade.

---

## Plugin Documentation Rule

When working on an official plugin, keep its public documentation in sync with the code.

This applies to changes in:

- New public client functions
- Removed public client functions
- Parameter changes in existing public client functions
- Behavioral changes that affect how an existing function should be used
- New plugin workflows that expose new capabilities worth documenting

Update the corresponding page in the `Plugins` section:

- `Git Plugin`
- `GitHub Plugin`
- `Jira Plugin`

At minimum, the documentation should reflect:

- The operation name
- How to call it
- Which parameters are required
- Which parameters are optional
- Any important usage constraints
