"""
Reasoning module for the multi-agent system.
This module defines the reasoning function that processes the formulated goals and produces results or actions.
"""

from multi_agent.agent.goal import Task
from multi_agent.agent.event import Message


def reasoning(
    goal: Task,
) -> Task | Message:
    """Placeholder for the reasoning step of the agent's processing pipeline."""
    return goal.result if goal.result else goal
