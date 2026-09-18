from pydantic import BaseModel, Field
from typing import List

class SafetyCheckResult(BaseModel):
    """Result from the Deterministic Safety Engine evaluating an ActionProposal."""
    is_approved: bool = Field(..., description="True if the action is approved, False otherwise.")
    proposal_version: str = Field(..., description="The state version the proposal was based on.")
    evaluated_against_version: str = Field(..., description="The current state version the safety engine checked against.")
    rejection_reasons: List[str] = Field(default_factory=list, description="List of reasons if the proposal was rejected.")
    applied_rules: List[str] = Field(default_factory=list, description="List of safety rules that were evaluated.")
