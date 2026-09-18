from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional
from backend.schemas.actions import InfrastructureAction

class ExecutionStatus(str, Enum):
    """The final status of an execution attempt."""
    SUCCESS = "success"
    FAILURE = "failure"

class ExecutionResult(BaseModel):
    """The result from the Action API after attempting to execute an approved proposal."""
    action: InfrastructureAction = Field(..., description="The action that was attempted.")
    target_service_id: str = Field(..., description="The target service ID.")
    status: ExecutionStatus = Field(..., description="Whether the execution succeeded or failed.")
    error_code: Optional[str] = Field(None, description="Error code if execution failed (e.g., 'capacity_unavailable').")
    error_message: Optional[str] = Field(None, description="Detailed error message if execution failed.")
    new_state_version: Optional[str] = Field(None, description="The new state version resulting from this action, if successful.")
