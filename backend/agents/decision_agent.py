from backend.schemas.workflow import InvestigationResult, DecisionResult
from backend.schemas.actions import InfrastructureAction, ActionProposal

class DecisionAgent:
    """
    Evaluates an InvestigationResult and generates a deterministic ActionProposal.
    The agent does not execute infrastructure actions; it only proposes them.
    """
    
    def decide(self, investigation: InvestigationResult) -> DecisionResult:
        issues = investigation.identified_issues
        obs = investigation.observation
        service_id = obs.service_id
        version = obs.state_version

        # C. Stale observation
        if "potentially stale observation" in issues:
            proposal = ActionProposal(
                action=InfrastructureAction.NO_ACTION,
                target_service_id=service_id,
                reason="The current state must be re-observed before taking a cost or scaling action because the observation is stale.",
                expected_effect="No change to infrastructure; await fresh metrics.",
                observation_version=version,
                confidence=1.0
            )
            return DecisionResult(investigation=investigation, proposal=proposal)

        # B. High resource/latency pressure
        if "scale-pressure conditions" in issues:
            proposal = ActionProposal(
                action=InfrastructureAction.SCALE_UP,
                target_service_id=service_id,
                reason="The objective is protecting service health/latency due to scale-pressure conditions.",
                expected_effect="Increased capacity to alleviate resource pressure and reduce latency.",
                observation_version=version,
                confidence=1.0
            )
            return DecisionResult(investigation=investigation, proposal=proposal)

        # A. Underutilized current observation
        if "potential underutilization" in issues or "excessive cost relative to utilization" in issues:
            proposal = ActionProposal(
                action=InfrastructureAction.SCALE_DOWN,
                target_service_id=service_id,
                reason="Cost-saving proposal: Service is currently underutilized relative to its cost.",
                expected_effect="Reduced cost by scaling down idle or over-provisioned resources.",
                observation_version=version,
                confidence=0.8
            )
            return DecisionResult(investigation=investigation, proposal=proposal)

        # D. Normal operation or unhandled
        proposal = ActionProposal(
            action=InfrastructureAction.NO_ACTION,
            target_service_id=service_id,
            reason="Service is operating normally or no actionable issues were found.",
            expected_effect="Maintains current stable state.",
            observation_version=version,
            confidence=1.0
        )

        return DecisionResult(investigation=investigation, proposal=proposal)
