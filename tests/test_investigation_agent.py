import pytest
from datetime import datetime, timezone, timedelta
from backend.schemas.metrics import ServiceObservation
from backend.agents.investigation_agent import InvestigationAgent

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
        state_version="v1"
    )

def test_scale_pressure_conditions_test_d():
    agent = InvestigationAgent()
    # Test D values: 91% CPU, 82% memory, 6400 RPM, 410 ms latency
    obs = create_observation(cpu=91.0, mem=82.0, traffic=6400, latency=410.0)
    result = agent.investigate(obs)
    
    assert "scale-pressure conditions" in result.identified_issues
    assert "high CPU pressure" not in result.identified_issues # Handled by scale pressure
    assert result.observation == obs

def test_underutilization():
    agent = InvestigationAgent()
    obs = create_observation(cpu=10.0, mem=15.0, traffic=500, cost=50.0)
    result = agent.investigate(obs)
    
    assert "potential underutilization" in result.identified_issues

def test_stale_observation_blocks_underutilization():
    agent = InvestigationAgent()
    # Old observation that would otherwise be underutilized
    obs = create_observation(cpu=10.0, mem=15.0, traffic=500, cost=50.0, age_seconds=600)
    result = agent.investigate(obs)
    
    assert "potentially stale observation" in result.identified_issues
    assert "potential underutilization" not in result.identified_issues
    assert "should not be used alone" in result.summary

def test_normal_operation():
    agent = InvestigationAgent()
    obs = create_observation(cpu=50.0, mem=50.0, traffic=3000, latency=100.0, cost=5.0)
    result = agent.investigate(obs)
    
    assert "normal operation" in result.identified_issues
