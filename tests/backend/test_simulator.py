"""Unit and integration tests for CloudEnvironmentSimulator and its API endpoints."""

import pytest
from fastapi.testclient import TestClient

from backend.api.deps import reset_dependencies
from backend.main import app
from backend.services.state_manager import ServiceNotFoundError, ServiceStateManager
from backend.simulator.cloud_simulator import CloudEnvironmentSimulator
from backend.simulator.scenarios import ScenarioType, get_scenario_definitions


@pytest.fixture
def state_manager() -> ServiceStateManager:
    manager = ServiceStateManager()
    manager.reset()
    manager.seed_default_services()
    return manager


@pytest.fixture
def simulator(state_manager: ServiceStateManager) -> CloudEnvironmentSimulator:
    return CloudEnvironmentSimulator(state_manager=state_manager)


@pytest.fixture
def client():
    reset_dependencies()
    with TestClient(app) as test_client:
        yield test_client
    reset_dependencies()


# ---------------------------------------------------------------------------
# Simulator Unit Tests
# ---------------------------------------------------------------------------

def test_load_all_scenarios(simulator: CloudEnvironmentSimulator) -> None:
    # 1. Normal
    normal_svcs = simulator.load_scenario(ScenarioType.NORMAL)
    assert simulator.active_scenario == ScenarioType.NORMAL
    assert len(normal_svcs) == 6

    # 2. Idle Waste
    idle_svcs = simulator.load_scenario(ScenarioType.IDLE_WASTE)
    assert simulator.active_scenario == ScenarioType.IDLE_WASTE
    cart = simulator.state_manager.get_service_or_raise("cart-service")
    assert cart.current_instances == 6
    assert cart.cpu_utilization_percent == 4.0

    # 3. Traffic Spike
    spike_svcs = simulator.load_scenario(ScenarioType.TRAFFIC_SPIKE)
    assert simulator.active_scenario == ScenarioType.TRAFFIC_SPIKE
    cart_spiked = simulator.state_manager.get_service_or_raise("cart-service")
    assert cart_spiked.traffic_rpm == 5000
    assert cart_spiked.cpu_utilization_percent == 92.0

    # 4. Degradation
    deg_svcs = simulator.load_scenario(ScenarioType.DEGRADATION)
    assert simulator.active_scenario == ScenarioType.DEGRADATION
    cart_deg = simulator.state_manager.get_service_or_raise("cart-service")
    assert cart_deg.healthy is False
    assert cart_deg.latency_ms == 450.0

    # 5. Protected Target
    prot_svcs = simulator.load_scenario(ScenarioType.PROTECTED_TARGET)
    assert simulator.active_scenario == ScenarioType.PROTECTED_TARGET
    db = simulator.state_manager.get_service_or_raise("prod-db")
    assert db.is_critical is True
    assert db.cost_per_hour == 9.00


def test_simulator_tick_physics(simulator: CloudEnvironmentSimulator) -> None:
    simulator.load_scenario(ScenarioType.NORMAL)
    assert simulator.tick_count == 0
    assert simulator.total_simulated_seconds == 0.0

    # Step clock by 60 seconds
    updated = simulator.tick(elapsed_seconds=60.0)
    assert simulator.tick_count == 1
    assert simulator.total_simulated_seconds == 60.0
    assert len(updated) == 6

    # Verify telemetry physics updated
    cart = simulator.state_manager.get_service_or_raise("cart-service")
    assert cart.cpu_utilization_percent is not None
    assert cart.cpu_utilization_percent > 0.0
    assert cart.state_version == "v2"


def test_stopped_service_tick_stays_zero(simulator: CloudEnvironmentSimulator) -> None:
    simulator.load_scenario(ScenarioType.NORMAL)
    # Stop analytics-worker
    simulator.state_manager.update_capacity("analytics-worker", current_instances=0)

    # Tick
    simulator.tick(elapsed_seconds=120.0)

    worker = simulator.state_manager.get_service_or_raise("analytics-worker")
    assert worker.current_instances == 0
    assert worker.traffic_rpm == 0
    assert worker.cpu_utilization_percent == 0.0
    assert worker.cost_per_hour == 0.0


def test_inject_traffic_spike(simulator: CloudEnvironmentSimulator) -> None:
    simulator.load_scenario(ScenarioType.NORMAL)
    spiked = simulator.inject_traffic_spike("cart-service", multiplier=4.0)

    assert spiked.traffic_rpm >= 4000
    assert spiked.cpu_utilization_percent >= 70.0
    assert spiked.state_version == "v2"

    with pytest.raises(ServiceNotFoundError):
        simulator.inject_traffic_spike("missing-service")


def test_inject_degradation_and_restore(simulator: CloudEnvironmentSimulator) -> None:
    simulator.load_scenario(ScenarioType.NORMAL)

    degraded = simulator.inject_degradation("cart-service")
    assert degraded.healthy is False
    assert degraded.latency_ms >= 350.0

    restored = simulator.restore_health("cart-service")
    assert restored.healthy is True
    assert restored.latency_ms <= 45.0


def test_simulator_status(simulator: CloudEnvironmentSimulator) -> None:
    simulator.load_scenario(ScenarioType.NORMAL)
    simulator.tick(60.0)
    status_data = simulator.get_status()

    assert status_data["active_scenario"] == "normal"
    assert status_data["tick_count"] == 1
    assert status_data["total_simulated_seconds"] == 60.0
    assert status_data["service_count"] == 6
    assert len(status_data["services"]) == 6


# ---------------------------------------------------------------------------
# Simulator API Endpoint Tests
# ---------------------------------------------------------------------------

def test_api_simulator_status_and_scenarios(client: TestClient) -> None:
    status_res = client.get("/api/simulator/status")
    assert status_res.status_code == 200
    data = status_res.json()
    assert data["active_scenario"] == "normal"
    assert data["service_count"] == 6

    scenarios_res = client.get("/api/simulator/scenarios")
    assert scenarios_res.status_code == 200
    scenarios = scenarios_res.json()
    assert "idle_waste" in scenarios
    assert "traffic_spike" in scenarios
    assert "degradation" in scenarios


def test_api_simulator_switch_scenario(client: TestClient) -> None:
    res = client.post("/api/simulator/scenario/idle_waste")
    assert res.status_code == 200

    status_res = client.get("/api/simulator/status")
    assert status_res.json()["active_scenario"] == "idle_waste"

    invalid_res = client.post("/api/simulator/scenario/unsupported_scenario")
    assert invalid_res.status_code == 400


def test_api_simulator_tick(client: TestClient) -> None:
    tick_res = client.post("/api/simulator/tick", json={"elapsed_seconds": 90.0})
    assert tick_res.status_code == 200

    status_res = client.get("/api/simulator/status")
    data = status_res.json()
    assert data["tick_count"] == 1
    assert data["total_simulated_seconds"] == 90.0


def test_api_simulator_inject_spike_and_degradation(client: TestClient) -> None:
    # Spike
    spike_res = client.post(
        "/api/simulator/inject/spike",
        json={"service_id": "cart-service", "multiplier": 3.5},
    )
    assert spike_res.status_code == 200
    assert spike_res.json()["traffic_rpm"] >= 1500

    # Degradation
    deg_res = client.post(
        "/api/simulator/inject/degradation",
        json={"service_id": "cart-service"},
    )
    assert deg_res.status_code == 200
    assert deg_res.json()["healthy"] is False

    # Restore
    rest_res = client.post(
        "/api/simulator/inject/restore",
        json={"service_id": "cart-service"},
    )
    assert rest_res.status_code == 200
    assert rest_res.json()["healthy"] is True
