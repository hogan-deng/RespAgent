"""Response typing schemas for generation module"""

from enum import Enum
from dataclasses import dataclass
from pydantic import BaseModel


class InitialType(str, Enum):
    """Enumeration for different initial types"""

    SINGLE = "single"
    MULTI = "multi"


class FeedbackType(str, Enum):
    """Enumeration for different feedback types"""

    GENERAL = "gen"
    SPECIFIC = "spec"


@dataclass(slots=True)
class AgentContext:
    """Context class for agent execution, containing relevant information and configurations."""

    model_name: str
    root_path: str
    initial_type: InitialType
    feedback_type: FeedbackType | None = None
    focus_revise: bool = False


class FeedbackItem(BaseModel):
    """Response schema for parsing the feedback output"""

    overview: str
    location: str
    media_query: str
    recommendation: str
    category: str
    severity: str


class ResponseFeedback(BaseModel):
    """Feedback response schema for parsing the model output"""

    feedbacks: list[FeedbackItem]


class ResponseHTML(BaseModel):
    """Response schema for parsing the model output containing HTML"""

    html: str
