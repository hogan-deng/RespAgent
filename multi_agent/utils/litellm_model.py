"""Module for generating content using LiteLLM models, including HTML generation with structured response parsing."""

import re
import logging
from time import time
from pathlib import Path

import litellm
from dotenv import load_dotenv

from common.logger import common_logger

# Load environment variables from .env file, model will pick up API KEY automatically.
load_dotenv()
# litellm.success_callback = ["lunary"]
# litellm.failure_callback = ["lunary"]
# litellm.callbacks = ["langfuse_otel"]
logging.getLogger("LiteLLM").setLevel(logging.ERROR)  # Disable LiteLLM warning logs

# Set of models that support flex tier service
FLEX_MODELS = {"gpt-5.2", "gpt-5.1", "gpt-5", "gpt-5-mini", "gpt-5-nano"}


async def generate_content(
    messages: list[dict],
    model: str = "openai/gpt-5-mini",
    config: dict | None = None,
):
    """Generate content from a text prompt using the specified model.

    Args:
        messages (list[dict]): The list of content dicts to send as input.
        model (str): The model to use for generation. Defaults to "openai/gpt-5-mini".
        config (dict): The additional configuration for generation.

    Returns:
        str: The generated content.
    """

    # Enable flex tier for openai models if user doesn't specify extra_body or set model name with "openai/"
    if not config or not config.get("extra_body", {}):
        if model in FLEX_MODELS:
            config = config or {}
            config["extra_body"] = {"service_tier": "flex"}

    try:
        common_logger.info("[MODEL] Generating content with model %s and config %s", model, config)
        response = await litellm.aresponses(
            model=model,
            input=messages,
            **(config or {}),
        )

        for output in response.output:
            if output.type == "message":
                return output.content[0].text  # Return the first message text
            if output.type == "function_call":
                return (output.name, output.arguments)

        return response
    except Exception as e:  # noqa: BLE001
        common_logger.error("[MODEL] Error during content generation with model %s: %s", model, e)
        # Store the output when error occurs
        model_name = re.sub(r"[/:]", "_", model)
        Path(".cache").mkdir(exist_ok=True)
        with open(f".cache/{model_name}.{int(time())}.txt", "w", encoding="utf-8") as f:
            f.write(str(e))

        raise e
