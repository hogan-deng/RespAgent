"""
This module defines the Task class and the goal formulation function for the multi-agent system."""

from enum import Enum
from dataclasses import dataclass

from multi_agent.agent.event import Event, Message


class TaskType(str, Enum):
    """Enumeration for different task types"""

    INITIAL = "initial"
    REVIEW = "review"
    REVISE = "revise"


@dataclass
class Task:
    """Task class for representing tasks in the system."""

    task_type: TaskType
    page_name: str
    iteration: int
    result: Message | None = None


def goal_formulation(message: Message) -> Task:
    """Formulate a task based on the incoming message."""

    task_type: TaskType
    if message.event_type == Event.ASGN_GENERATE:
        task_type = TaskType.INITIAL
    elif message.event_type == Event.ASGN_REVIEW:
        task_type = TaskType.REVIEW
    elif message.event_type == Event.ASGN_REVISE:
        task_type = TaskType.REVISE
    else:
        raise ValueError(f"Unknown event type: {message.event_type}")

    goal_task = Task(
        task_type=task_type,
        page_name=message.page_name,
        iteration=message.iteration,
    )
    return goal_task
