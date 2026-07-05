"""JSON serialization utilities for evaluation outputs."""

from dataclasses import asdict, is_dataclass

import numpy as np
from pydantic import BaseModel


def json_serializable(o):
    """Convert dataclass or Pydantic model to JSON serializable format."""

    if is_dataclass(o):
        return asdict(o)
    if isinstance(o, BaseModel):
        return o.model_dump()
    if isinstance(o, set):
        return list(o)
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")
