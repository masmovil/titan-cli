"""
Docker Exceptions

Custom exceptions for Docker operations.
"""


class DockerError(Exception):
    """Base exception for Docker errors"""
    pass


class DockerClientError(DockerError):
    """Docker client initialization or configuration error"""
    pass


class DockerCommandError(DockerError):
    """Docker CLI command failed"""
    pass


class DockerComposeError(DockerError):
    """Docker Compose operation failed"""
    pass


class DockerBuildError(DockerError):
    """Docker image build failed"""
    pass


class DockerBuildTargetNotFoundError(DockerError):
    """Requested build target is not defined in the project configuration"""
    pass


class DockerServiceGroupNotFoundError(DockerError):
    """Requested service group is not defined in the project configuration"""
    pass
