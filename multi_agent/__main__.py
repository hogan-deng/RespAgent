"""Main entry point for the RespAgent system"""

import re
import asyncio
import argparse

from tqdm import tqdm

from common.logger import common_logger
from common.config import get_html_name_list
from multi_agent.utils.typings import InitialType, FeedbackType
from multi_agent.agent.core import AgentContext, CoreAgent
from multi_agent.agent.event import EventBus, Message, Event


class FrontEndAgent(CoreAgent):
    """Agent responsible for generating HTML content based on assigned tasks."""

    def __init__(self, ctx: AgentContext):
        registered_events = {Event.ASGN_GENERATE, Event.ASGN_REVISE}
        super().__init__("front_end_agent", ctx, registered_events)


class ReviewAgent(CoreAgent):
    """Agent responsible for reviewing generated HTML content and providing feedback for revisions."""

    def __init__(self, ctx: AgentContext):
        registered_events = {Event.ASGN_REVIEW}
        super().__init__("review_agent", ctx, registered_events)


class TaskBoard:
    """Track page workflow state and drive next-step routing."""

    def __init__(
        self,
        page_list: list[str],
        is_review_enabled: bool,
        max_iteration: int,
    ):
        self._name = "task_board"
        self._tasks_to_process = page_list
        self._enable_review = is_review_enabled
        self._max_iteration = max_iteration

        self._event_handler: EventBus | None = None

        self._finished_pages: set[str] = set()
        self._done_event = asyncio.Event()

        self._status = {"init": ("", 0, ""), "rev": ("", 0, ""), "rvs": ("", 0, "")}
        self._progress = tqdm(total=len(page_list), desc="Overall Progress", unit="page")

    def connect(self, event_bus: EventBus) -> None:
        """Connect to event bus."""
        self._event_handler = event_bus
        self._event_handler.subscribe(self._name, self.on_message)

    def start(self) -> None:
        """Publish initial generation assignments."""
        for page_name in self._tasks_to_process:
            msg = Message(Event.ASGN_GENERATE, self._name, page_name, iteration=1)
            self._event_handler.publish(msg)

    async def wait_until_done(self) -> None:
        """Wait until all pages reach terminal state."""
        if not self._tasks_to_process:
            return
        await self._done_event.wait()

    def on_message(self, msg: Message) -> None:
        """Process response event, update state, and publish next assignment if needed."""
        self._update_progress(msg)

        if self._is_terminal(msg):
            self._mark_finished(msg.page_name)
            return

        next_msg = self._build_next_message(msg)
        if next_msg is not None:
            self._event_handler.publish(next_msg)

    def _is_terminal(self, msg: Message) -> bool:
        """Return True when page workflow should stop."""
        if not self._enable_review:
            return msg.event_type == Event.RESP_GENERATE
        if msg.event_type in {Event.ERROR, Event.NONE_REVIEW}:
            return True
        return msg.event_type == Event.RESP_REVISE and msg.iteration >= self._max_iteration

    def _build_next_message(self, msg: Message) -> Message | None:
        """Return next assignment from current response."""
        page_name = msg.page_name
        iteration = msg.iteration

        if msg.event_type == Event.RESP_GENERATE:
            if self._enable_review:
                return Message(Event.ASGN_REVIEW, self._name, page_name, iteration)

        if msg.event_type == Event.RESP_REVIEW:
            return Message(Event.ASGN_REVISE, self._name, page_name, iteration)

        if msg.event_type == Event.RESP_REVISE and iteration < self._max_iteration:
            return Message(Event.ASGN_REVIEW, self._name, page_name, iteration + 1)

        return None

    def _mark_finished(self, page_name: str) -> None:
        """Mark a page complete and set done event when all are complete."""
        self._progress.update(1)
        self._finished_pages.add(page_name)
        if len(self._finished_pages) >= len(self._tasks_to_process):
            self._done_event.set()

    def _update_progress(self, msg: Message) -> None:
        """Update and print progress state."""

        key = None
        if msg.event_type in {Event.ASGN_GENERATE, Event.RESP_GENERATE}:
            key = "init"
        elif msg.event_type in {Event.ASGN_REVIEW, Event.RESP_REVIEW, Event.NONE_REVIEW}:
            key = "rev"
        elif msg.event_type in {Event.ASGN_REVISE, Event.RESP_REVISE}:
            key = "rvs"

        if key is not None:
            self._status[key] = (msg.page_name, msg.iteration, msg.event_type.value)

        event_display = [
            f"{key.upper()}: {item[0]}#{item[1]} {item[2].rsplit(' ', maxsplit=1)[-1].lower()}"
            for key, item in self._status.items()
            if item[1] > 0
        ]
        self._progress.set_description(" ▶ ".join(event_display))


async def multi_process(
    ctx: AgentContext,
    page_list: list[str],
    max_iteration: int = 1,
):
    """Main function to set up and run the agent workflow for generating and reviewing HTML pages."""

    if len(page_list) == 0:
        print(
            f"All pages for '{ctx.initial_type.value}'"
            + (f" with feedback '{ctx.feedback_type.value}'" if ctx.feedback_type else "")
            + " have already been processed."
        )
        return

    agent_a = FrontEndAgent(ctx)
    agent_b = ReviewAgent(ctx)

    event_bus = EventBus()
    agent_a.connect(event_bus)
    agent_b.connect(event_bus)

    # Start the agents and publish tasks to the event bus
    await asyncio.gather(agent_a.start(), agent_b.start())

    # Initialize the task board to track progress and connect it to the event bus
    task_board = TaskBoard(page_list, is_review_enabled=bool(ctx.feedback_type), max_iteration=max_iteration)
    task_board.connect(event_bus)
    task_board.start()

    # Wait global workflow completion (not per-queue transient empty)
    await task_board.wait_until_done()

    # Stop the agents after all tasks are completed
    await asyncio.gather(agent_a.stop(), agent_b.stop())


def _handle_exception(loop, context):
    """Handle exceptions in background tasks."""
    exception = context.get("exception")
    if exception and isinstance(exception, RuntimeError):
        if "Event loop is closed" in str(exception) or "Bad file descriptor" in str(exception):
            common_logger.warning("[ASYNC] SSL transport warning (non-critical): %s", exception)
            return

    # Log other exceptions normally
    common_logger.error("[ASYNC] Exception in event loop: %s", context)


if __name__ == "__main__":
    HELP_INFO = """
Generate HTML files based on a agent workflow prompt type with iterative refinement.
Usage:
  python -m multi_agent --model MODEL_NAME [--count EXEC_COUNT] [--file FILE_NAME] [--version VERSION] [--iter ITERATION]
Example:
  python -m multi_agent --count 5
"""
    # Initialize the parser
    parser = argparse.ArgumentParser(description=HELP_INFO)
    parser.add_argument(
        "--initial",
        choices=[InitialType.SINGLE, InitialType.MULTI],
        type=str,
        default=InitialType.MULTI.value,
        help="Initial type to process (single or multi, default: multi)",
    )
    parser.add_argument(
        "--feedback",
        choices=[FeedbackType.GENERAL, FeedbackType.SPECIFIC],
        type=str,
        help="Feedback type to process (general or specific, default: no feedback)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-5.1-codex-mini",
        help="Model to use for generation (default: gpt-5.1-codex-mini)",
    )
    parser.add_argument(
        "--focus", action="store_true", help="Whether to focus on revision based on feedback (default: False)"
    )
    parser.add_argument("--count", type=int, help="Number of files to process (default: all)")
    parser.add_argument("--file", type=str, help="Specific file name to process (e.g., 62.html)")
    parser.add_argument("--iteration", type=int, default=1, help="Number of iterations for revision (default: 1)")
    parser.add_argument("--version", type=int, default=1, help="Number of versions to generate (default: 1)")

    # Parse the arguments
    args = parser.parse_args()
    arg_name_list = get_html_name_list(args.file)
    arg_model_dir = re.sub(r"\w+/", "", args.model)
    arg_root_path = f"results/{arg_model_dir}_{args.version:02X}"

    if args.count:
        arg_name_list = arg_name_list[: args.count]

    arg_initial_type = InitialType(args.initial)
    arg_feedback_type = FeedbackType(args.feedback) if args.feedback else None
    arg_agent_ctx = AgentContext(args.model, arg_root_path, arg_initial_type, arg_feedback_type, args.focus)
    # asyncio.run(multi_process(arg_agent_ctx, arg_name_list, args.iteration))

    # Create event loop and set exception handler
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(_handle_exception)
        loop.run_until_complete(multi_process(arg_agent_ctx, arg_name_list, args.iteration))
    finally:
        loop.close()
