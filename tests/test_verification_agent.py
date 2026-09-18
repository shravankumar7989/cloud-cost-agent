import pytest
from datetime import datetime, timezone
from backend.schemas.metrics import ServiceObservation
from backend.schemas.actions import InfrastructureAction, ActionProposal
from backend.schemas.workflow import DecisionResult, InvestigationResult
from backend.schemas.safety import SafetyCheckResult
from backend.schemas.execution import ExecutionResult, ExecutionStatus
from backend.agents.verification_agent import VerificationAgent

def mock_decision(action: InfrastructureAction) -> DecisionResult:
    obs = ServiceObservation(
        service_id="test-service",
        cpu_utilization_percent=50.0,
        memory_utilization_percent=50.0,
        traffic_rpm=5000,
        latency_ms=100.0,
        cost_per_hour=20.0,
        observation_timestamp=datetime.now(timezone.utc),
        state_version="v1"
    )
    inv = InvestigationResult(observation=obs, identified_issues=[], summary="")
    prop = ActionProposal(
        action=action,
        target_service_id="test-service",
        reason="",
        expected_effect="",
        observation_version="v1",
        confidence=1.0
    )
    return DecisionResult(investigation=inv, proposal=prop)

def test_approved_scale_up_success():
    agent = VerificationAgent()
    dec = mock_decision(InfrastructureAction.SCALE_UP)
    safe = SafetyCheckResult(is_approved=True, proposal_version="v1", evaluated_against_version="v1", rejection_reasons=[], applied_rules=[])
    exec_res = ExecutionResult(action=InfrastructureAction.SCALE_UP, target_service_id="test-service", status=ExecutionStatus.SUCCESS)
    
    result = agent.verify(dec, safe, exec_res)
    assert result.is_successful is True
    assert "Successfully executed" in result.verification_notes
    assert "scale_up" in result.verification_notes

def test_approved_scale_up_capacity_unavailable_failure():
    agent = VerificationAgent()
    dec = mock_decision(InfrastructureAction.SCALE_UP)
    safe = SafetyCheckResult(is_approved=True, proposal_version="v1", evaluated_against_version="v1", rejection_reasons=[], applied_rules=[])
    exec_res = ExecutionResult(action=InfrastructureAction.SCALE_UP, target_service_id="test-service", status=ExecutionStatus.FAILURE, error_code="capacity_unavailable")
    
    result = agent.verify(dec, safe, exec_res)
    assert result.is_successful is False
    assert "capacity_unavailable" in result.verification_notes

def test_approved_scale_down_success():
    agent = VerificationAgent()
    dec = mock_decision(InfrastructureAction.SCALE_DOWN)
    safe = SafetyCheckResult(is_approved=True, proposal_version="v1", evaluated_against_version="v1", rejection_reasons=[], applied_rules=[])
    exec_res = ExecutionResult(action=InfrastructureAction.SCALE_DOWN, target_service_id="test-service", status=ExecutionStatus.SUCCESS)
    
    result = agent.verify(dec, safe, exec_res)
    assert result.is_successful is True
    assert "scale_down" in result.verification_notes

def test_rejected_safety_check():
    agent = VerificationAgent()
    dec = mock_decision(InfrastructureAction.SCALE_DOWN)
    safe = SafetyCheckResult(is_approved=False, proposal_version="v1", evaluated_against_version="v1", rejection_reasons=["High CPU"], applied_rules=[])
    
    result = agent.verify(dec, safe)
    assert result.is_successful is False
    assert "not authorized by the Safety Engine" in result.verification_notes
    assert "No infrastructure changes were made" in result.verification_notes

def test_approved_no_action():
    agent = VerificationAgent()
    dec = mock_decision(InfrastructureAction.NO_ACTION)
    safe = SafetyCheckResult(is_approved=True, proposal_version="v1", evaluated_against_version="v1", rejection_reasons=[], applied_rules=[])
    
    result = agent.verify(dec, safe)
    assert result.is_successful is True
    assert "No infrastructure change was required" in result.verification_notes

def test_successful_execution_with_new_state_version():
    agent = VerificationAgent()
    dec = mock_decision(InfrastructureAction.SCALE_UP)
    safe = SafetyCheckResult(is_approved=True, proposal_version="v1", evaluated_against_version="v1", rejection_reasons=[], applied_rules=[])
    exec_res = ExecutionResult(action=InfrastructureAction.SCALE_UP, target_service_id="test-service", status=ExecutionStatus.SUCCESS, new_state_version="v2")
    
    post_obs = ServiceObservation(
        service_id="test-service", cpu_utilization_percent=50.0, memory_utilization_percent=50.0,
        traffic_rpm=5000, latency_ms=100.0, cost_per_hour=20.0, observation_timestamp=datetime.now(timezone.utc),
        state_version="v2"
    )

    result = agent.verify(dec, safe, exec_res, post_obs)
    assert result.is_successful is True
    assert "New state version reported" in result.verification_notes
    assert "confirms the state version changed to v2" in result.verification_notes

def test_failed_execution_with_another_error_code():
    agent = VerificationAgent()
    dec = mock_decision(InfrastructureAction.RESIZE)
    safe = SafetyCheckResult(is_approved=True, proposal_version="v1", evaluated_against_version="v1", rejection_reasons=[], applied_rules=[])
    exec_res = ExecutionResult(action=InfrastructureAction.RESIZE, target_service_id="test-service", status=ExecutionStatus.FAILURE, error_code="timeout", error_message="API Gateway timeout")
    
    result = agent.verify(dec, safe, exec_res)
    assert result.is_successful is False
    assert "timeout" in result.verification_notes
    assert "API Gateway timeout" in result.verification_notes
