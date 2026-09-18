from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class InfrastructureAction(str, Enum):
    """Allowed infrastructure actions that can be proposed."""
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    RESIZE = "resize"
    STOP_IDLE_SERVICE = "stop_idle_service"
    DELAY_BATCH = "delay_batch"
    NO_ACTION = "no_action"

class ActionProposal(BaseModel):
    """Represents an LLM's proposed action. This is NOT an executed action."""
    action: InfrastructureAction = Field(..., description="The proposed infrastructure action.")
    target_service_id: str = Field(..., description="The service on which the action should be performed.")
    reason: str = Field(..., description="The LLM's reasoning for proposing this action.")
    expected_effect: str = Field(..., description="The expected outcome or effect of this action.")
    observation_version: str = Field(..., description="The state version this proposal is based upon (to prevent stale execution).")
    confidence: float = Field(..., ge=0.0, le=1.0, description="The LLM's confidence level in this proposal.")
    target_instances: Optional[int] = Field(default=None, description="Optional target instance count for scaling actions.")
