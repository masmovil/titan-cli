# Docker Built-in Workflows

The Docker plugin currently ships six workflows: four for the compose
lifecycle (up, down, status, prune) plus one for building/pushing images and
one for host-wide container cleanup.

## `docker-up`

Starts Docker Compose services (all services, or a project-configured `service_groups` entry) and shows their status.

**Source workflow:** `plugins/titan-plugin-docker/titan_plugin_docker/workflows/docker-up.yaml`

### Default flow

1. `docker.select_service_group`
2. `docker.compose_up`
3. `docker.compose_status`

### Related public steps

- `select_service_group`
- `compose_up`
- `compose_status`

## `docker-down`

Stops Docker Compose services. Presents every service as a checked-by-default
checklist - unchecking a service keeps it running. Leaving everything checked
runs a full `docker compose down`; unchecking some services stops only the
rest. Unchecking everything exits without stopping anything.

**Source workflow:** `plugins/titan-plugin-docker/titan_plugin_docker/workflows/docker-down.yaml`

### Default flow

1. `docker.select_services_to_stop`
2. `docker.compose_down`
3. `docker.compose_status`

### Related public steps

- `select_services_to_stop`
- `compose_down`
- `compose_status`

## `docker-status`

Shows the current state of every Docker Compose service for this project -
no selection step, just a straight status report.

**Source workflow:** `plugins/titan-plugin-docker/titan_plugin_docker/workflows/docker-status.yaml`

### Default flow

1. `docker.compose_status`

### Related public steps

- `compose_status`

## `docker-build-push`

Builds (and pushes, per target config) every Docker image configured for the project.

**Source workflow:** `plugins/titan-plugin-docker/titan_plugin_docker/workflows/docker-build-push.yaml`

### Default flow

1. `docker.build_push_images`

### Related public steps

- `build_push_images`

## `docker-prune`

Shows a host-wide disk usage breakdown, lets you pick which resource
categories to clean up (nothing selected by default, since pruning is
destructive), prunes them, then shows disk usage again so you can see what
was reclaimed.

**Source workflow:** `plugins/titan-plugin-docker/titan_plugin_docker/workflows/docker-prune.yaml`

### Default flow

1. `docker.disk_usage`
2. `docker.select_prune_targets`
3. `docker.prune_resources`
4. `docker.disk_usage`

### Related public steps

- `disk_usage`
- `select_prune_targets`
- `prune_resources`

## `docker-clean-containers`

Lists every container on the host (not just this project's) and lets you
remove selected stopped ones. Running containers are shown for context but
cannot be selected for removal.

**Source workflow:** `plugins/titan-plugin-docker/titan_plugin_docker/workflows/docker-clean-containers.yaml`

### Default flow

1. `docker.select_containers_to_remove`
2. `docker.remove_containers`

### Related public steps

- `select_containers_to_remove`
- `remove_containers`
