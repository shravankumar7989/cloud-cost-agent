import pytest
from datetime import datetime, timezone, timedelta
from backend.schemas.metrics import ServiceObservation
from backend.schemas.actions import InfrastructureAction
from backend.orchestrator.orchestrator import Orchestrator

def create_observation(
    cpu=50.0,
    mem=50.0,
    traffic=5000,
    latency=100.0,
    cost=20.0,
    age_seconds=0
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
        state_version="v2"
    )

def test_orchestrator_normal_observation():
    orchestrator = Orchestrator()
    obs = create_observation(cpu=50.0, mem=50.0, traffic=3000, latency=100.0)
    result = orchestrator.run(obs)
    
    assert result.proposal.action == InfrastructureAction.NO_ACTION
    assert result.proposal.target_service_id == "test-service"
    assert result.proposal.observation_version == "v2"

def test_orchestrator_underutilized_observation():
    orchestrator = Orchestrator()
    obs = create_observation(cpu=10.0, mem=15.0, traffic=500, cost=50.0)
    result = orchestrator.run(obs)
    
    assert result.proposal.action in [InfrastructureAction.SCALE_DOWN, InfrastructureAction.RESIZE]
    assert result.proposal.target_service_id == "test-service"
    assert result.proposal.observation_version == "v2"

def test_orchestrator_scale_pressure_test_d():
    orchestrator = Orchestrator()
    # Test D pressure observation (CPU 91%, memory 82%, traffic 6400 RPM, latency 410ms)
    obs = create_observation(cpu=91.0, mem=82.0, traffic=6400, latency=410.0)
    result = orchestrator.run(obs)
    
    assert result.proposal.action == InfrastructureAction.SCALE_UP
    assert result.proposal.target_service_id == "test-service"
    assert result.proposal.observation_version == "v2"

def test_orchestrator_stale_observation():
    orchestrator = Orchestrator()
    obs = create_observation(age_seconds=600)
    result = orchestrator.run(obs)
    
    assert result.proposal.action == InfrastructureAction.NO_ACTION
    assert "stale" in result.investigation.identified_issues[0] or "stale" in result.proposal.reason
    assert result.proposal.target_service_id == "test-service"
    assert result.proposal.observation_version == "v2"
