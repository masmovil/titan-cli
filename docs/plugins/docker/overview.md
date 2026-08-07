# Docker Plugin

The Docker plugin provides Titan's Docker Compose lifecycle and image build/push
surface. It exposes:

- a high-level `DockerClient` for direct use from Titan code
- reusable workflow `steps` such as `compose_up`, `compose_status`, and `build_push_images`
- the built-in `docker-up` and `docker-build-push` workflows

The plugin has no built-in notion of any specific project's services or
images: `service_groups` (named groups of compose service names) and
`build_targets` (buildable images) are entirely defined by each project's
`.titan/config.toml`.

## Requirements

To use the Docker plugin in a project:

- Enable the `docker` plugin in `.titan/config.toml`
- Install Docker (with the `compose` and `buildx` CLI plugins) and make sure it is available in `PATH`

Example project configuration:

```toml
[plugins.docker]
enabled = true

[plugins.docker.config]
compose_file = "docker-compose.yml"

[plugins.docker.config.service_groups]
infra = ["db", "cache"]

[[plugins.docker.config.build_targets]]
name = "backend"
dockerfile = "packages/backend/Dockerfile"
context = "."
image = "ghcr.io/org/app-backend"
target = "production"
platforms = "linux/amd64"
push = true
```

### Build target fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | yes | - | Unique name for the target within the project (also what `docker-build-push` accepts to build a single image) |
| `dockerfile` | yes | - | Path to the Dockerfile, relative to the project root |
| `image` | yes | - | Image reference to build/push, without tag (e.g. `ghcr.io/org/app-backend`) |
| `context` | no | `"."` | Build context path, relative to the project root |
| `target` | no | none | Dockerfile build stage to target (e.g. `production`) |
| `platforms` | no | builder native | Comma-separated `--platform` list for buildx |
| `tag` | no | `"latest"` | Tag applied to the built image |
| `push` | no | `false` | Push to the registry after building |

#### About `platforms`

When `platforms` is omitted, the plugin passes no `--platform` flag and buildx
builds for the builder's native platform.

Set it explicitly when the deploy target differs from the machine doing the
build (e.g. `platforms = "linux/amd64"` on an arm64 laptop deploying to an
amd64 server), or to publish a multi-arch image
(`platforms = "linux/amd64,linux/arm64"`).

Every platform in the list that the build host does not natively match is built
under QEMU emulation, which costs a full slow build per platform - dependencies
are recompiled or re-downloaded for that architecture. Only list architectures
you actually deploy.

## Public surfaces

- [Client API](./client-api.md): direct Python methods exposed by `DockerClient`
- [Workflow Steps](./workflow-steps.md): public reusable workflow steps grouped by functionality
- [Built-in Workflows](./built-in-workflows.md): workflows shipped by the plugin

## Accessing the client

In Titan code, the public entry point is the Docker plugin client:

```python
docker_plugin = config.registry.get_plugin("docker")
client = docker_plugin.get_client()
```

The client returns `ClientResult[...]` values. In practice, this means each call can succeed with data or return an error result.

## Public workflow steps

The Docker plugin exposes these reusable public steps through `get_steps()`:

- `select_service_group`
- `select_services_to_stop`
- `compose_up`
- `compose_down`
- `compose_status`
- `build_push_images`
- `disk_usage`
- `select_prune_targets`
- `prune_resources`
- `select_containers_to_remove`
- `remove_containers`
