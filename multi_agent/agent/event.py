"""Event handling classes for agent communication."""

from enum import Enum
from typing import Callable
from dataclasses import dataclass


class Event(str, Enum):
    """Enumeration for different event types"""

    # General events
    ERROR = "ERROR"
    # Initial assignment and response events
    ASGN_GENERATE = "GENERATE START"
    RESP_GENERATE = "GENERATE DONE"
    # Feedback assignment and response events
    ASGN_REVIEW = "REVIEW START"
    RESP_REVIEW = "REVIEW DONE"
    NONE_REVIEW = "REVIEW NONE"
    # Revision assignment and response events
    ASGN_REVISE = "REVISE START"
    RESP_REVISE = "REVISE DONE"


@dataclass
class Message:
    """Message class for communication between agents via the Event bus."""

    event_type: Event
    sender_id: str
    page_name: str
    iteration: int


class EventBus:
    """Event bus for agents to publish and subscribe to messages."""

    def __init__(self):
        self._subscribers: dict[str, Callable[[Message], None]] = {}

    def subscribe(self, client_id: str, handler: Callable[[Message], None]) -> None:
        """Subscribe an agent to receive messages."""
        self._subscribers[client_id] = handler

    def publish(self, message: Message) -> None:
        """Publish a message to all subscribers except the sender."""

        for client_id, handler in self._subscribers.items():
            if client_id != message.sender_id:
                handler(message)
