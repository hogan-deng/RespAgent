"""Shared framework for implementing multi-agent systems."""

import asyncio

from multi_agent.utils.typings import AgentContext
from multi_agent.agent.event import Event, EventBus, Message
from multi_agent.agent.goal import Task, goal_formulation
from multi_agent.agent.reasoning import reasoning
from multi_agent.agent.interaction import environment_interaction


class CoreAgent:
    """
    Shared staged execution model:
    1) Event Processing
    2) Goal Formulation
    3) Reasoning
    4) Action Execution & Environment Interaction
    """

    def __init__(self, name: str, ctx: AgentContext, registered_events: set[Event] | None = None):
        self._name = name
        self._ctx = ctx

        self._registered_events = registered_events or set()
        self._event_handler: EventBus | None = None

        self._worker_thread: asyncio.Task | None = None
        self._worker_queue: asyncio.Queue[Message] = asyncio.Queue()

    def connect(self, event_bus: EventBus) -> None:
        """Connect the agent to the event bus for communication."""
        self._event_handler = event_bus
        self._event_handler.subscribe(self._name, self.on_message)

    def on_message(self, message: Message) -> None:
        """Handle incoming messages from the event bus and enqueue them for processing."""
        if message.event_type in self._registered_events:
            self._worker_queue.put_nowait(message)

    async def start(self) -> None:
        """Start the agent's event processing loop."""
        if self._worker_thread is None:
            self._worker_thread = asyncio.create_task(self.event_processing())

    async def stop(self) -> None:
        """Stop the agent's event processing loop."""
        if self._worker_thread is None:
            return
        self._worker_thread.cancel()
        try:
            await self._worker_thread
        except asyncio.CancelledError:
            pass
        self._worker_thread = None

    async def event_processing(self) -> None:
        """Asynchronous loop to process incoming messages."""
        while True:
            message = await self._worker_queue.get()
            try:
                # Republish the message to trigger any state updates in the task board before processing
                message.sender_id = self._name  # Update sender to self for downstream processing
                self._event_handler.publish(message)

                goal = goal_formulation(message)
                while True:
                    plan = reasoning(goal)
                    if isinstance(plan, Task):
                        goal = await environment_interaction(self._name, self._ctx, plan)
                    elif isinstance(plan, Message):
                        self._event_handler.publish(plan)
                        break
            finally:
                self._worker_queue.task_done()
