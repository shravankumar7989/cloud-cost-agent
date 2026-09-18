import pytest
from datetime import datetime, timezone
from backend.schemas.metrics import ServiceObservation
from backend.schemas.workflow import InvestigationResult
from backend.schemas.actions import InfrastructureAction
from backend.agents.decision_agent import DecisionAgent

def create_investigation_result(issues: list[str]) -> InvestigationResult:
    obs = ServiceObservation(
        service_id="test-service",
        cpu_utilization_percent=50.0,
        memory_utilization_percent=50.0,
        traffic_rpm=5000,
        latency_ms=100.0,
        cost_per_hour=20.0,
        observation_timestamp=datetime.now(timezone.utc),
        state_version="v2"
    )
    return InvestigationResult(
        observation=obs,
        identified_issues=issues,
        summary="Test summary."
    )

def test_stale_observation_proposes_no_action():
    agent = DecisionAgent()
    investigation = create_investigation_result(["potentially stale observation", "potential underutilization"])
    result = agent.decide(investigation)
    
    assert result.proposal.action == InfrastructureAction.NO_ACTION
    assert "re-observed" in result.proposal.reason
    assert result.proposal.observation_version == "v2"

def test_scale_pressure_proposes_scale_up():
    agent = DecisionAgent()
    investigation = create_investigation_result(["scale-pressure conditions"])
    result = agent.decide(investigation)
    
    assert result.proposal.action == InfrastructureAction.SCALE_UP
    assert "health" in result.proposal.reason.lower() or "latency" in result.proposal.reason.lower()
    assert result.proposal.observation_version == "v2"

def test_underutilization_proposes_scale_down():
    agent = DecisionAgent()
    investigation = create_investigation_result(["potential underutilization"])
    result = agent.decide(investigation)
    
    assert result.proposal.action in [InfrastructureAction.SCALE_DOWN, InfrastructureAction.RESIZE]
    assert "cost-saving" in result.proposal.reason.lower()
    assert result.proposal.observation_version == "v2"

def test_normal_operation_proposes_no_action():
    agent = DecisionAgent()
    investigation = create_investigation_result(["normal operation"])
    result = agent.decide(investigation)
    
    assert result.proposal.action == InfrastructureAction.NO_ACTION
    assert result.proposal.observation_version == "v2"
