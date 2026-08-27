# Secrets & Security

Titan's rule for secrets has one sentence: **no Titan API ever returns a secret
string**. Not to steps, not to plugins, not to screens. Everything below exists
to make that sentence structurally true, not a convention.

## The trust boundary

All raw secret handling lives in **`titan_cli/core/security/`**:

- `_vault.py` — the private `SecretManager` (env → `.titan/secrets.env` →
  OS keyring cascade). Only this package may import it or `keyring`.
- `broker.py` — `SecretBroker`, `SecretRef`, `SecretBrokerFactory`.
- `sessions.py` — authenticated-object factories.
- `execution.py` — redacted subprocess primitives.
- `redaction.py` — global redaction registry + leak detection.
- `sensitive.py` — `SensitiveValue` for plugin-derived material.

The boundary is CI-enforced by `tests/core/security/test_architecture.py`:
importing `keyring` or `_vault` outside the package fails the suite, as does
reaching `._vault` as an attribute through a broker.

## What a step or plugin gets: `SecretBroker`

Steps receive `ctx.secret_broker`, already scoped to the plugin's namespace
(`titan.plugins.<name>`; project/user steps get `titan.project`/`titan.user`).
Plugins receive one in `initialize(config, broker)`. Its full public API
(pinned by an allowlist test — adding a method is a deliberate act):

| Method | What it does |
|---|---|
| `exists(key)` | Whether the key resolves (whole cascade). |
| `source(key)` | Which level would resolve it: `"env"` / `"project"` / `"keyring"` / `None`. Metadata only. |
| `store(key, value)` | Store a value you already hold → opaque `SecretRef`. Rejects empty/whitespace. |
| `prompt_and_store(key, prompt)` | Ask the user (TUI password prompt) and store. `None` on cancel. |
| `delete(key)` | Delete from the keyring. Returns `False` if an env/project copy still shadows it. |
| `create_client(key, builder)` | Constructor injection for SDKs that need the credential at construction (Slack `WebClient`, Jira client). Runtime `SecretLeakError` guard if the builder returns the value. |
| `run_with_secret_stdin(key, prompt, cmd)` | Secret → stdin (e.g. `gpg --passphrase-fd 0`). Stale-keyring retry semantics; never deletes when the value came from env/project or the command itself couldn't run (126/127). |
| `run_with_secret_env(key, var, cmd)` | Secret → one env var in a minimal allowlisted environment. |
| `with_secret_tempfile(key, callback)` | Secret → 0600 tempfile, guaranteed deletion. |

There is deliberately no `get()`. If you think you need the value, you need
one of the factories or use-primitives instead.

For sessions/providers built inside the boundary:
`create_authenticated_session(ref, scheme)` (a `requests.Session` with the
`Authorization` header set) and `create_ai_provider(connection_id, cfg)`
(the AI chain's provider factory).

## Namespacing — honest limits

Namespaces scope **only the keyring level**. The env-var and
`.titan/secrets.env` levels are global by design (CI/CD, team-shared), so any
broker can resolve `GITHUB_TOKEN` if it's exported. And the OS keyring itself
has no per-namespace ACL: any code running in the user's session can `import
keyring`. What the boundary guarantees is immunity to **accidental** exposure
through Titan's APIs; malicious in-process code is the (future) sandbox's job.

Legacy migration: reads that miss under a scoped namespace fall back to the
pre-broker service names (`titan`/`ragnarok`) and **copy** (never move) the
entry to its new home, so older installed Titans keep working. `delete()`
sweeps the legacy copies only when the scoped namespace holds its own copy
(ownership evidence).

## Derived material: `SensitiveValue`

Protecting a passphrase does not protect what the passphrase unlocked. When a
plugin derives sensitive material itself (a decrypted service-account JSON),
wrap it: `SensitiveValue(payload)`. It cannot be pickled, deep-copied, or
JSON-serialized, its repr is redacted, and string payloads register for
redaction. Access is explicit: `.reveal()` — call it as late as possible
(ideally inside a client constructor).

## Result metadata is checked

`Success`/`Skip`/`Exit` scan their `metadata` at construction and raise
`SecretLeakError` if a registered secret string appears anywhere in it —
including dict keys and attributes of plain objects/models. Opaque carriers
(`SensitiveValue`, `SecretRef`) are allowed; raw strings are not. If a step
needs to pass sensitive material forward, wrap it.

## Redaction

Every value the vault dereferences (and stores) is registered. `redact(text)`
masks registered values ≥4 chars in command echoes, output, and errors.
Detection (`contains_secret`/`find_secret_in`) keeps all lengths — short
values match with token boundaries to avoid false positives.

## Plugin trust & static scan

`core/plugins/trust.py` classifies every plugin: `official` (entry point owned
by the official package — the name alone is spoofable), `community`
(repo-pinned stable channel or unrecognized package), `local` (dev_local
path), `verified` (reserved). Non-entry-point sources are AST-scanned at load
for `keyring` imports, `_vault` imports, and `SecretManager` references —
including `tests/` (importable too), with unreadable/unparseable files
reported as findings. The scan **warns, never blocks**: findings are logged
and shown in the plugin management screen. Plugin names `core`/`project`/
`user` are rejected at registration (they map onto Titan's own namespaces).

Config:

```toml
[security]
community_plugins = "in_process"   # future: worker | sandbox
```

## Rules for step/plugin authors

1. Never ask for a secret value. Use `create_client`, a session factory, or a
   use-primitive.
2. Never put a raw secret (or anything derived from one) in `ctx.data` or
   result metadata — wrap derived material in `SensitiveValue`.
3. Prompting: `prompt_and_store` via the broker, not `ask_password` + manual
   storage (the executor wires the prompter for you).
4. Subprocesses that need a credential: use the use-primitives; never argv
   (visible in `ps`), never the inherited environment.
