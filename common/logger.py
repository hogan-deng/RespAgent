"""Logging utilities for the project."""

import logging
from pathlib import Path

# Configure logging
LOG_LEVEL = logging.INFO
log_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def create_logger(name: str, log_file: str, log_level: int = LOG_LEVEL) -> logging.Logger:
    """Create and configure a logger."""
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    # file_handler.setLevel(log_level)
    file_handler.setFormatter(log_formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.ERROR)  # Only log errors to the console
    stream_handler.setFormatter(log_formatter)

    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger


Path(".cache").mkdir(parents=True, exist_ok=True)
# Create a logger for the HTML builder module
agent_logger = create_logger("AgentLogger", ".cache/agent.log")
# Create a logger for the common module
common_logger = create_logger("CommonLogger", ".cache/common.log")
