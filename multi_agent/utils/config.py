"""Configuration Loader for Generation Module"""

from pathlib import Path

import yaml

config_path = Path(__file__).parent / "config.yaml"
with open(config_path, "r", encoding="utf-8") as f:
    config_data = yaml.safe_load(f)

SYSTEM_PROMPT_INITIAL_SINGLE = config_data["prompts"]["single"]
SYSTEM_PROMPT_INITIAL_MULTIPLE = config_data["prompts"]["multiple"]
SYSTEM_PROMPT_FEEDBACK_GENERAL = config_data["prompts"]["feedback_general"]
SYSTEM_PROMPT_FEEDBACK_SPECIFIC = config_data["prompts"]["feedback_specific"]
