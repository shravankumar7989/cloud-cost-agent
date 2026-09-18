from pydantic import BaseModel, Field
from typing import Optional, List
from backend.schemas.metrics import ServiceObservation
from backend.schemas.actions import ActionProposal
from backend.schemas.safety import SafetyCheckResult
from backend.schemas.execution import ExecutionResult

class InvestigationResult(BaseModel):
    """Result of the Investigation Agent analyzing an observation."""
    observation: ServiceObservation = Field(..., description="The observation that was investigated.")
    identified_issues: List[str] = Field(default_factory=list, description="List of identified issues (e.g., high latency, underutilization).")
    summary: str = Field(..., description="Text summary of the investigation findings.")

class DecisionResult(BaseModel):
    """Result of the Decision Agent generating a proposal."""
    investigation: InvestigationResult = Field(..., description="The investigation context.")
    proposal: ActionProposal = Field(..., description="The structured action proposal.")

class VerificationResult(BaseModel):
    """Result of verifying the actual outcome of the workflow."""
    decision: DecisionResult = Field(..., description="The decision context.")
    safety_check: SafetyCheckResult = Field(..., description="The safety evaluation result.")
    execution: Optional[ExecutionResult] = Field(None, description="The execution result, if the action was approved and attempted.")
    is_successful: bool = Field(..., description="True if the action was executed successfully OR if it was correctly rejected/no_action.")
    verification_notes: str = Field(..., description="Notes regarding the final outcome.")

class WorkflowReport(BaseModel):
    """The final report encompassing the entire agent workflow execution."""
    workflow_id: str = Field(..., description="Unique identifier for this workflow run.")
    initial_observation: ServiceObservation = Field(..., description="The observation that triggered this workflow.")
    final_verification: VerificationResult = Field(..., description="The final verified outcome of the workflow.")
