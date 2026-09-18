from typing import Optional
from backend.schemas.workflow import DecisionResult, VerificationResult
from backend.schemas.safety import SafetyCheckResult
from backend.schemas.execution import ExecutionResult, ExecutionStatus
from backend.schemas.metrics import ServiceObservation
from backend.schemas.actions import InfrastructureAction

class VerificationAgent:
    """
    Deterministic Verification Agent that validates the entire workflow outcome.
    It does not execute actions or use LLMs.
    """
    
    def verify(
        self,
        decision: DecisionResult,
        safety_check: SafetyCheckResult,
        execution: Optional[ExecutionResult] = None,
        post_execution_observation: Optional[ServiceObservation] = None
    ) -> VerificationResult:
        
        notes_parts = []
        is_successful = False

        action = decision.proposal.action
        target_service = decision.proposal.target_service_id

        # 1. Safety Rejection
        if not safety_check.is_approved:
            notes_parts.append("Execution was not authorized by the Safety Engine.")
            notes_parts.append("No infrastructure changes were made.")
            is_successful = False

        # 4. No Action
        elif action == InfrastructureAction.NO_ACTION:
            notes_parts.append(f"Action '{action.value}' was approved by the Safety Engine.")
            notes_parts.append("No infrastructure change was required.")
            is_successful = True

        # Handle Execution (for actions other than NO_ACTION)
        else:
            if execution is None:
                notes_parts.append("Execution result is missing despite safety approval for an active infrastructure change.")
                is_successful = False
            else:
                # 2. Execution Failure
                if execution.status == ExecutionStatus.FAILURE:
                    is_successful = False
                    if execution.error_code == "capacity_unavailable":
                        notes_parts.append(f"Execution failed (Code: capacity_unavailable) for action '{action.value}' on service '{target_service}'.")
                    else:
                        err_code = execution.error_code or "Unknown"
                        err_msg = execution.error_message or "No message provided."
                        notes_parts.append(f"Execution failed (Code: {err_code}, Message: {err_msg}) for action '{action.value}' on service '{target_service}'.")
                
                # 3. Execution Success
                elif execution.status == ExecutionStatus.SUCCESS:
                    is_successful = True
                    notes_parts.append(f"Successfully executed action '{action.value}' on target service '{target_service}'.")
                    if execution.new_state_version:
                        notes_parts.append(f"New state version reported by execution layer: {execution.new_state_version}.")

        # 5. Post-Execution Observation
        if post_execution_observation:
            observed_version = post_execution_observation.state_version
            if execution and execution.new_state_version:
                if observed_version == execution.new_state_version:
                    notes_parts.append(f"Post-execution observation confirms the state version changed to {observed_version}.")
                else:
                    notes_parts.append(f"Post-execution observation state version ({observed_version}) does not match expected new version ({execution.new_state_version}).")
            else:
                notes_parts.append(f"Post-execution observation recorded with state version: {observed_version}.")

        return VerificationResult(
            decision=decision,
            safety_check=safety_check,
            execution=execution,
            is_successful=is_successful,
            verification_notes=" ".join(notes_parts)
        )
