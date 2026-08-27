"""Mapper for Docker Compose status: Network model → UI model."""
from ..network.compose_status import NetworkComposeStatus
from ..view.compose_status import UIComposeService, UIComposeStatus


def from_network_compose_status(network_status: NetworkComposeStatus) -> UIComposeStatus:
    """
    Transform network compose status model to UI compose status model.

    Args:
        network_status: Raw status data from `docker compose ps`

    Returns:
        Formatted UI status model with icons and a summary
    """
    ui_services = [
        UIComposeService(
            service=service.service,
            container_name=service.container_name,
            image=service.image,
            state=service.state,
            status=service.status,
            health=service.health,
            state_icon="✓" if service.state == "running" else "✗",
        )
        for service in network_status.services
    ]

    running_count = sum(1 for service in ui_services if service.state == "running")
    total_count = len(ui_services)
    all_running = total_count > 0 and running_count == total_count

    return UIComposeStatus(
        services=ui_services,
        all_running=all_running,
        summary=f"{running_count}/{total_count} running",
    )
