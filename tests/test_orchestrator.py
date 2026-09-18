import pytest
from datetime import datetime, timezone, timedelta
from backend.schemas.metrics import ServiceObservation
from backend.schemas.actions import ActionProposal, InfrastructureAction
from backend.schemas.execution import ExecutionResult, ExecutionStatus
from backend.schemas.workflow import WorkflowReport
from backend.orchestrator.orchestrator import Orchestrator

def create_observation(
    cpu=50.0, mem=50.0, traffic=5000, latency=100.0, cost=20.0, age_seconds=0, version="v1"
) -> ServiceObservation:
    timestamp = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return ServiceObservation(
        service_id="test-service",
        cpu_utilization_percent=cpu,
        memory_utilization_percent=mem,
        traffic_rpm=traffic,
        latency_ms=latency,
        cost_per_hour=cost,
        observation_timestamp=timestamp,
        state_version=version
    )

class MockExecutor:
    def __init__(self, status=ExecutionStatus.SUCCESS, error_code=None, new_version=None):
        self.call_count = 0
        self.status = status
        self.error_code = error_code
        self.new_version = new_version

    def __call__(self, proposal: ActionProposal) -> ExecutionResult:
        self.call_count += 1
        return ExecutionResult(
            action=proposal.action,
            target_service_id=proposal.target_service_id,
            status=self.status,
            error_code=self.error_code,
            new_state_version=self.new_version
        )

class MockObserver:
    def __init__(self, obs: ServiceObservation):
        self.call_count = 0
        self.obs = obs
        
    def __call__(self, target_service_id: str) -> ServiceObservation:
        self.call_count += 1
        return self.obs


def test_a_underutilized_service():
    executor = MockExecutor()
    orchestrator = Orchestrator(executor=executor)
    obs = create_observation(cpu=10.0, mem=15.0, traffic=500, cost=50.0)
    report = orchestrator.run(obs)
    
    assert report.final_verification.decision.proposal.action in [InfrastructureAction.SCALE_DOWN, InfrastructureAction.RESIZE]
    assert report.final_verification.safety_check.is_approved is True
    assert executor.call_count == 1
    assert report.final_verification.is_successful is True

def test_b_sudden_traffic_scale_pressure():
    executor = MockExecutor()
    orchestrator = Orchestrator(executor=executor)
    obs = create_observation(cpu=91.0, mem=82.0, traffic=6400, latency=410.0)
    report = orchestrator.run(obs)
    
    assert report.final_verification.decision.proposal.action == InfrastructureAction.SCALE_UP
    assert report.final_verification.safety_check.is_approved is True
    assert executor.call_count == 1
    assert report.final_verification.is_successful is True

def test_c_stale_observation():
    executor = MockExecutor()
    orchestrator = Orchestrator(executor=executor)
    obs = create_observation(cpu=10.0, mem=10.0, traffic=500, age_seconds=600)
    report = orchestrator.run(obs)
    
    assert report.final_verification.decision.proposal.action == InfrastructureAction.NO_ACTION
    assert report.final_verification.safety_check.is_approved is True
    assert executor.call_count == 0
    assert report.final_verification.is_successful is True

def test_d_test_d_capacity_unavailable():
    executor = MockExecutor(status=ExecutionStatus.FAILURE, error_code="capacity_unavailable")
    orchestrator = Orchestrator(executor=executor)
    obs = create_observation(cpu=91.0, mem=82.0, traffic=6400, latency=410.0)
    report = orchestrator.run(obs)
    
    assert report.final_verification.decision.proposal.action == InfrastructureAction.SCALE_UP
    assert report.final_verification.safety_check.is_approved is True
    assert executor.call_count == 1
    assert report.final_verification.is_successful is False
    assert "capacity_unavailable" in report.final_verification.verification_notes
    assert report.final_verification.execution.status == ExecutionStatus.FAILURE

def test_e_safety_rejection():
    class RogueDecisionAgent:
        def decide(self, inv):
            from backend.schemas.workflow import DecisionResult
            from backend.schemas.actions import ActionProposal, InfrastructureAction
            prop = ActionProposal(
                action=InfrastructureAction.SCALE_DOWN,
                target_service_id=inv.observation.service_id,
                reason="Rogue agent",
                expected_effect="Scale down despite high CPU",
                observation_version=inv.observation.state_version,
                confidence=1.0
            )
            return DecisionResult(investigation=inv, proposal=prop)
            
    executor = MockExecutor()
    orchestrator = Orchestrator(decision_agent=RogueDecisionAgent(), executor=executor)
    obs = create_observation(cpu=95.0) 
    report = orchestrator.run(obs)
    
    assert report.final_verification.decision.proposal.action == InfrastructureAction.SCALE_DOWN
    assert report.final_verification.safety_check.is_approved is False
    assert executor.call_count == 0
    assert report.final_verification.is_successful is False

def test_f_re_observation():
    executor = MockExecutor(new_version="v2")
    post_obs = create_observation(version="v2")
    observer = MockObserver(post_obs)
    
    orchestrator = Orchestrator(executor=executor, observer=observer)
    obs = create_observation(cpu=91.0, mem=82.0, traffic=6400, latency=410.0, version="v1")
    report = orchestrator.run(obs)
    
    assert executor.call_count == 1
    assert observer.call_count == 1
    assert report.final_verification.is_successful is True
    assert "v2" in report.final_verification.verification_notes
