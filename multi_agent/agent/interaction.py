"""Agent-Environment Interaction Logic for Responsive Web Design Generation and Feedback"""

import json
import base64
from pathlib import Path


from bs4 import BeautifulSoup, Tag

from common.logger import agent_logger
from common.json_output import json_serializable
from common.config import PageConfig, get_page_config
from common.screenshots import capture_page_screenshots

from multi_agent.utils.litellm_model import generate_content
from multi_agent.utils.typings import AgentContext, InitialType, FeedbackType, ResponseHTML, ResponseFeedback
from multi_agent.agent.event import Message, Event
from multi_agent.agent.goal import Task, TaskType
from multi_agent.utils.config import (
    SYSTEM_PROMPT_INITIAL_SINGLE,
    SYSTEM_PROMPT_INITIAL_MULTIPLE,
    SYSTEM_PROMPT_FEEDBACK_GENERAL,
    SYSTEM_PROMPT_FEEDBACK_SPECIFIC,
)


def _build_image_payload(image_path: str, mime_type="image/png"):
    """
    Build an 'input_image' payload dictionary with a data URL.
    Raises FileNotFoundError if the file does not exist.
    """
    path = Path(image_path)

    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return {
        "type": "input_image",
        "image_url": f"data:{mime_type};base64,{encoded}",
    }


def _read_html_content(html_path: Path) -> str:
    """Read the HTML content from the specified path. Raises FileNotFoundError if the file does not exist."""
    if not html_path.exists():
        raise FileNotFoundError(f"Generated HTML not found for refinement: {html_path}")
    html_content = html_path.read_text(encoding="utf-8")
    if html_content.strip() == "":
        raise ValueError(f"Generated HTML is empty for refinement: {html_path}")
    return html_content


def _write_html_content(html_content: str, output_path: Path):
    """Write the generated HTML content to the specified output path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")


def _read_feedback_content(feedback_path: Path) -> list[dict]:
    """Read the feedback content from the specified path. Returns an empty list if the file does not exist."""
    if not feedback_path.exists():
        raise FileNotFoundError(f"Feedback not found for refinement: {feedback_path}")

    with open(feedback_path, "r", encoding="utf-8") as f:
        feedback_list = json.load(f)
    return feedback_list


def _write_feedback_content(feedback_content: list[dict], output_path: Path):
    """Write the generated feedback content to the specified output path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(feedback_content, f, default=json_serializable, indent=2)


def _get_initial_prompt_messages(
    ctx: AgentContext,
    page_config: PageConfig,
) -> str:
    """Build the prompt messages for HTML generation based on the prototype images."""

    user_content: list[dict] = [
        {"type": "input_text", "text": "Generate an HTML page based on the following screenshots."}
    ]

    for size, image_path in page_config.prototypes.items():
        if ctx.initial_type == InitialType.SINGLE and size != "1280x720":
            continue
        image_payload = _build_image_payload(image_path)
        user_content.append({"type": "input_text", "text": f"prototype image - {size}"})
        user_content.append(image_payload)

    content = SYSTEM_PROMPT_INITIAL_MULTIPLE if ctx.initial_type == InitialType.MULTI else SYSTEM_PROMPT_INITIAL_SINGLE
    return [{"role": "system", "content": content}, {"role": "user", "content": user_content}]


def _get_refine_prompt_message(
    ctx: AgentContext,
    page_config: PageConfig,
    feedback_path: Path,
    focus_revise: bool = False,
) -> list[dict]:
    """Build the prompt messages for HTML refinement."""

    # Build initial messages (system prompt + user message with prototype images)
    messages = _get_initial_prompt_messages(ctx, page_config)

    # Append the previously generated HTML as the assistant turn so the model
    # has full context of what it produced before being asked to refine it
    html_path = page_config.get_html_path()
    html_content = _read_html_content(html_path)
    messages.append({"role": "assistant", "content": html_content})

    # Normalize feedback items (accept FeedbackItem instances or raw dicts)
    feedback_content = _read_feedback_content(feedback_path)
    normalized_feedback: list[dict] = []
    for idx, item in enumerate(feedback_content, start=1):
        if isinstance(item, dict):
            fb = item
        else:
            # Fallback to string representation
            fb = {"overview": str(item)}

        # Build a concise, structured text block per feedback item
        fb_text_lines = [
            f"Feedback {idx}:",
            f"Overview: {fb.get('overview', '')}",
            f"Location: {fb.get('location', '')}",
            f"Media Query: {fb.get('media_query', '')}",
            f"Recommendation: {fb.get('recommendation', fb.get('modify', ''))}",
        ]
        normalized_feedback.append({"type": "input_text", "text": "\n".join(fb_text_lines)})

    # Construct the revision instruction based on whether focus revision is enabled
    revise_prompt = (
        (
            "Please produce an improved single HTML+CSS file that revises only the code related to the feedback "
            + "and double-checks that the changes do not affect any correct parts. Respond with the full HTML content."
        )
        if focus_revise
        else (
            "Please produce an improved single HTML+CSS file that applies the feedback while "
            + "preserving responsive behavior. Respond with the full HTML content."
        )
    )

    # Append the feedback and instruction as a single user message (preserves existing image payloads)
    instruction = [{"type": "input_text", "text": revise_prompt}]
    user_content = instruction + normalized_feedback
    messages.append({"role": "user", "content": user_content})

    return messages


def _get_feedback_prompt_messages(ctx: AgentContext, page_config: PageConfig) -> str:
    """Build the feedback prompt messages based on the prototype images and generated HTML."""

    user_content: list[dict] = [
        {"type": "input_text", "text": "Review the generated HTML page based on the following screenshots."}
    ]

    # Append prototype images
    for size, image_path in page_config.prototypes.items():
        image_payload = _build_image_payload(image_path)
        user_content.append({"type": "input_text", "text": f"prototype image - {size}"})
        user_content.append(image_payload)

    # Append the generated HTML screenshots
    for size, image_path in page_config.screenshots.items():
        image_payload = _build_image_payload(image_path)
        user_content.append({"type": "input_text", "text": f"generated HTML screenshot - {size}"})
        user_content.append(image_payload)

    content = (
        SYSTEM_PROMPT_FEEDBACK_SPECIFIC
        if ctx.feedback_type == FeedbackType.SPECIFIC
        else SYSTEM_PROMPT_FEEDBACK_GENERAL
    )
    return [{"role": "system", "content": content}, {"role": "user", "content": user_content}]


def _assign_meta_ids(html_content: str) -> str:
    """Assign sequential data-meta-id attributes (hex, 3-digit uppercase) to <body>
    and its descendant tags. Returns the modified HTML string.
    `start` sets the initial counter (default 0).
    """
    bs = BeautifulSoup(html_content, "html.parser")
    body = bs.body
    if body is None:
        return html_content

    tags = [body] + [node for node in body.descendants if isinstance(node, Tag)]
    for idx, tag in enumerate(tags):
        tag["data-meta-id"] = f"{idx:03X}"

    return str(bs)


async def _generate_html(messages: list[dict], model: str) -> str:
    """Generate one HTML pages from prompt and optional screenshot.

    Args:
        messages (list[dict]): The list of content dicts to send as input.
        model (str): The model to use for generation. Defaults to "openai/gpt-5-mini".

    Returns:
        str: The generated HTML content.
    """

    response = await generate_content(
        model=model,
        messages=messages,
        config={"text_format": ResponseHTML},
    )

    if response:
        result: ResponseHTML = json.loads(response, object_hook=lambda d: ResponseHTML(**d))
        if result.html.strip():
            html = _assign_meta_ids(result.html)
            return html

    raise ValueError("Received empty response from model when generating HTML content.")


async def _generate_feedback(messages: list[dict], model: str) -> list[dict]:
    """Generate feedback content from prompt and optional screenshot.

    Args:
        messages (list[dict]): The list of content dicts to send as input.
        model (str): The model to use for generation. Defaults to "openai/gpt-5-mini".

    Returns:
        list[dict]: The generated feedback content.
    """

    response = await generate_content(
        model=model,
        messages=messages,
        config={"text_format": ResponseFeedback},
    )

    if response:
        try:
            response = json.loads(response)
            feedback_items = list(response["feedbacks"])
            feedback_items.sort(key=lambda x: int(s) if (s := x.get("severity", "")).isdigit() else -1, reverse=True)
            return feedback_items
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise ValueError(f"Failed to parse feedback response: {e}\nResponse content: {response}") from e

    raise ValueError("Received empty response from model when generating feedback content.")


async def environment_interaction(identity: str, ctx: AgentContext, goal: Task) -> Task:
    """Main interaction function for the agent to interact with the environment based on the given goal and context."""

    initial_folder = f"{ctx.root_path}/{ctx.initial_type.value}"
    initial_page_config = get_page_config(initial_folder, goal.page_name, 1)

    feedback_suffix = f"_{ctx.feedback_type.value}" if ctx.feedback_type else ""
    focus_suffix = "_focus" if ctx.focus_revise else ""
    current_folder = f"{ctx.root_path}/{ctx.initial_type.value}{feedback_suffix}{focus_suffix}"

    previous_page_config = get_page_config(current_folder, goal.page_name, goal.iteration - 1)
    feedback_path = previous_page_config.get_feedback_path()

    current_page_config = get_page_config(current_folder, goal.page_name, goal.iteration)
    revised_html_path = current_page_config.get_html_path()

    # For the first iteration, there is no previous page to refer to, so we use the initial page config as baseline.
    if goal.iteration == 1:
        previous_page_config = initial_page_config
        # If focus_revise is enabled, adopt the none-focus feedback as the baseline for revision.
        if focus_suffix:
            none_focus_feedback_path = Path(str(feedback_path).replace(focus_suffix, ""))
            if none_focus_feedback_path.exists():
                feedback_path = none_focus_feedback_path

    event_type: Event = None
    iteration = goal.iteration
    try:
        if goal.task_type == TaskType.INITIAL:
            if not initial_page_config.get_html_path().exists():
                prompt_msg = _get_initial_prompt_messages(ctx, initial_page_config)
                html_content = await _generate_html(prompt_msg, ctx.model_name)
                _write_html_content(html_content, initial_page_config.get_html_path())
                await capture_page_screenshots(initial_page_config)  # Capture screenshots after initial generation
                agent_logger.info("Initial HTML generated for page: %s", goal.page_name)
            event_type = Event.RESP_GENERATE
        elif goal.task_type == TaskType.REVISE:
            if not revised_html_path.exists():
                prompt_msg = _get_refine_prompt_message(ctx, previous_page_config, feedback_path, ctx.focus_revise)
                html_content = await _generate_html(prompt_msg, ctx.model_name)
                _write_html_content(html_content, revised_html_path)
                await capture_page_screenshots(current_page_config)  # Capture screenshots after revision
                agent_logger.info("Revised HTML generated for page: %s", goal.page_name)
            event_type = Event.RESP_REVISE
        elif goal.task_type == TaskType.REVIEW:
            if not feedback_path.exists():
                await capture_page_screenshots(previous_page_config)
                prompt_msg = _get_feedback_prompt_messages(ctx, previous_page_config)
                feedback_content = await _generate_feedback(prompt_msg, ctx.model_name)
                _write_feedback_content(feedback_content, feedback_path)
                agent_logger.info("Feedback generated for page: %s", goal.page_name)
            else:
                feedback_content = _read_feedback_content(feedback_path)
            event_type = Event.RESP_REVIEW if feedback_content else Event.NONE_REVIEW
    except (FileNotFoundError, ValueError) as e:
        event_type = Event.ERROR
        agent_logger.error("Error during environment interaction: %s", e)

    goal.result = Message(
        event_type=event_type,
        iteration=iteration,
        sender_id=identity,
        page_name=goal.page_name,
    )
    return goal
