# Docker Workflow Steps

The Docker plugin exposes reusable public workflow steps through `DockerPlugin.get_steps()`.

## Summary

| Step | Group | Used by built-in workflows |
|------|-------|-----------------------------|
| `select_service_group` | Compose | `docker-up` |
| `select_services_to_stop` | Compose | `docker-down` |
| `compose_up` | Compose | `docker-up` |
| `compose_down` | Compose | `docker-down` |
| `compose_status` | Compose | `docker-up`, `docker-down`, `docker-status` |
| `build_push_images` | Build | `docker-build-push` |
| `disk_usage` | Prune | `docker-prune` |
| `select_prune_targets` | Prune | `docker-prune` |
| `prune_resources` | Prune | `docker-prune` |
| `select_containers_to_remove` | Containers | `docker-clean-containers` |
| `remove_containers` | Containers | `docker-clean-containers` |

## Compose

Use these steps to resolve which services to operate on and drive the compose lifecycle.

- `select_service_group`: let the user pick a project-configured `service_groups` entry (or "All services"), saving `docker_services` to the workflow context
- `select_services_to_stop`: checkbox list of every compose service, all checked by default; unchecking one keeps it running. If everything stays checked, resolves to a full `docker compose down`; otherwise stops just the checked subset. Exits early (nothing to do) if the user unchecks everything.
- `compose_up`: start the services in `docker_services` (all services if absent/empty)
- `compose_down`: stop the services in `docker_services` (the whole project if absent/empty)
- `compose_status`: show a table of service state/status/health for `docker_services` (all services if absent/empty), saving `docker_compose_status` to the workflow context. With no prior step setting `docker_services`, it reports on every service - this is what powers the standalone `docker-status` workflow.

## Build

Use this step to build (and push, per target config) configured Docker images.

- `build_push_images`: build every configured `build_targets` entry, or a single one when `build_target_name` is set in the workflow context, saving `docker_build_results` to the workflow context. Streams `docker buildx build` output into a live, read-only text area per target (mouse-selectable and copyable) instead of a plain spinner.

## Prune

Use these steps to inspect and reclaim host-wide Docker disk usage. Unlike the Compose steps above, these are not scoped to this project's compose file - they report on the whole Docker host.

- `disk_usage`: show a table of Docker's disk usage breakdown (images, containers, local volumes, build cache) via `docker system df`, saving `docker_disk_usage` to the workflow context
- `select_prune_targets`: checkbox list of resource categories (stopped containers, dangling images, build cache, unused volumes), nothing checked by default since pruning is destructive. Exits early if nothing is selected. Note Docker itself refuses to remove a volume still attached to any container, so `volumes` never touches an in-use volume.
- `prune_resources`: run `docker ... prune` for each target in `prune_targets`, saving `docker_prune_results` to the workflow context

## Containers

Use these steps to inspect and clean up containers across the whole host, not just this project.

- `select_containers_to_remove`: list every container on the host (running and stopped) for context, then offer a checkbox list of the stopped ones for removal, nothing checked by default. Exits early if there are no stopped containers, or if nothing is selected.
- `remove_containers`: remove the containers in `docker_container_ids` via `docker rm` (without `-f`, so Docker itself refuses to remove a still-running container)
