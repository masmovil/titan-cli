"""Core models for the Slack plugin baseline."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class NetworkSlackChannel:
    """Raw Slack channel data normalized from the Web API."""

    id: str
    name: str
    is_channel: bool = True
    is_private: bool = False


@dataclass
class NetworkSlackUser:
    """Raw Slack user data normalized from the Web API."""

    id: str
    name: str
    real_name: Optional[str] = None
    is_bot: bool = False
    is_active: bool = True


@dataclass
class UISlackUser:
    """User model returned by Slack client and services."""

    id: str
    name: str
    real_name: Optional[str] = None
    is_bot: bool = False
    is_active: bool = True


@dataclass
class SlackMessageRef:
    """Stable reference to a posted Slack message."""

    channel: str
    ts: str
    thread_ts: Optional[str] = None
    permalink: Optional[str] = None


@dataclass
class NetworkSlackMessage:
    """Raw Slack message data normalized from the Web API."""

    ts: str
    text: str
    user: Optional[str] = None
    bot_id: Optional[str] = None
    username: Optional[str] = None
    thread_ts: Optional[str] = None
    reply_count: int = 0
    subtype: Optional[str] = None


@dataclass
class UISlackChannel:
    """Channel model returned by Slack client and services."""

    id: str
    name: str
    is_channel: bool = True
    is_private: bool = False


@dataclass
class UISlackMessage:
    """Message model returned by Slack client and services."""

    ts: str
    text: str
    user: Optional[str] = None
    bot_id: Optional[str] = None
    username: Optional[str] = None
    thread_ts: Optional[str] = None
    reply_count: int = 0
    subtype: Optional[str] = None


@dataclass
class UISlackAuth:
    """Auth identity model returned by Slack auth validation."""

    user_id: Optional[str] = None
    user: Optional[str] = None
    team_id: Optional[str] = None
    team: Optional[str] = None
    url: Optional[str] = None
    bot_id: Optional[str] = None


@dataclass
class UISlackTarget:
    """Reusable Slack target model for users and channels."""

    target_type: str
    target_id: str
    target_name: str
    team_id: Optional[str] = None
    connection_id: Optional[str] = None


@dataclass
class UISlackConversation:
    """Conversation model returned when Slack opens or resolves a DM."""

    id: str
    is_im: bool = False
    user_id: Optional[str] = None
    team_id: Optional[str] = None


@dataclass
class UISlackPostedMessage:
    """Posted Slack message metadata returned by message sending operations."""

    channel: str
    ts: str
    text: Optional[str] = None
    thread_ts: Optional[str] = None
