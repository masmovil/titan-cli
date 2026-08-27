# Docker Client API

The Docker plugin adds Docker Compose lifecycle management and image build/push
operations to Titan through a high-level client and reusable workflows.

This page documents the plugin from a functional point of view, while also
showing how each capability is called and which parameters it needs.

---

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
push = true
```

---

## Accessing the client

In Titan code, the public entry point is the Docker plugin client:

```python
docker_plugin = config.registry.get_plugin("docker")
client = docker_plugin.get_client()
```

The client returns `ClientResult[...]` values. In practice, this means each call can succeed with data or return an error result.

The client also carries the project's configured `service_groups` and
`build_targets` as plain attributes (`client.service_groups`,
`client.build_targets`), so steps and operations can resolve them without a
separate config lookup.

---

## Compose operations

### Start services

Starts compose services in the background.

**Call:**

```python
client.compose_up(services=["db", "cache"])
```

**Parameters:**

- `services` (list of str, optional): Service names to start. Omit or pass an empty list to start every service in the compose file.
- `detach` (bool, optional): Run containers in the background. Defaults to `True`.

### Stop services

Stops compose services.

**Call:**

```python
client.compose_down(services=["db", "cache"])
```

**Parameters:**

- `services` (list of str, optional): Service names to stop. Omit or pass an empty list to stop (`down`) the whole project; a non-empty list runs `stop` on just those services.

### Get compose status

Returns the state of compose services (running/exited, health, status text).

**Call:**

```python
client.compose_status(services=["db"])
```

**Parameters:**

- `services` (list of str, optional): Service names to inspect. Omit or pass an empty list to inspect every service.

---

## Build operations

### Build (and optionally push) an image

Builds a single configured image with `docker buildx build`, covering both
single-platform and multi-platform builds through the same code path.

**Call:**

```python
from titan_cli.core.plugins.models import DockerBuildTargetConfig

target = DockerBuildTargetConfig(
    name="backend",
    dockerfile="packages/backend/Dockerfile",
    context=".",
    image="ghcr.io/org/app-backend",
    target="production",
    platforms="linux/amd64",
    tag="latest",
    push=True,
)
client.build_target(target)

# Stream build output line by line instead of waiting for the final result
client.build_target(target, on_output=lambda line: print(line))
```

**Parameters:**

- `target` (`DockerBuildTargetConfig`, required): the build target to build. Typically resolved from `client.build_targets` (project configuration) rather than constructed by hand. When its `platforms` is unset, no `--platform` flag is passed and buildx builds for the builder's native platform (see [Build target fields](./overview.md#build-target-fields)).
- `on_output` (callable, optional): called with each line of `docker buildx build` output as it streams (stdout+stderr merged, in emission order). Omit to just run the build and get the final result.

---

## Prune operations

These operate on the whole Docker host, not just this project - Docker doesn't scope disk usage or prune targets to a single compose file.

### Get disk usage

Returns a breakdown of Docker's disk usage (images, containers, local volumes, build cache) via `docker system df`.

**Call:**

```python
client.disk_usage()
```

**Parameters:**

- No parameters.

### Prune resources

Removes unused resources for the given categories.

**Call:**

```python
client.prune(["containers", "images"])
```

**Parameters:**

- `targets` (list of str, required): subset of `"containers"`, `"images"`, `"build_cache"`, `"volumes"`. `"images"` only removes dangling (untagged) images. Docker itself refuses to remove a volume still attached to any container, so `"volumes"` never touches an in-use volume.

---

## Container operations

These also operate on the whole Docker host - every container, not just this project's compose services.

### List containers

Lists every container on the host, running or stopped.

**Call:**

```python
client.list_containers()
```

**Parameters:**

- No parameters.

### Remove containers

Removes the given containers via `docker rm` (without `-f`).

**Call:**

```python
client.remove_containers(["abc123", "def456"])
```

**Parameters:**

- `container_ids` (list of str, required): container IDs or names to remove. Docker itself refuses (surfaced as a `ClientError`) if any of them is still running.
