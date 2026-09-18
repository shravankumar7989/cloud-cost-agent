"""Predefined demo scenarios for the Cloud Environment Simulator."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List

from backend.schemas.service_state import ServiceState


class ScenarioType(str, Enum):
    """Supported cloud simulation scenario types."""

    NORMAL = "normal"
    IDLE_WASTE = "idle_waste"
    TRAFFIC_SPIKE = "traffic_spike"
    DEGRADATION = "degradation"
    PROTECTED_TARGET = "protected_target"


@dataclass
class SimulatorScenario:
    """Configuration definition for a simulator scenario."""

    scenario_type: ScenarioType
    name: str
    description: str
    services: List[ServiceState]


def get_scenario_definitions() -> Dict[ScenarioType, SimulatorScenario]:
    """Retrieve catalog of all scenario configurations."""
    return {
        ScenarioType.NORMAL: SimulatorScenario(
            scenario_type=ScenarioType.NORMAL,
            name="Normal Balanced Workload",
            description="Baseline operational state across all production and background services.",
            services=[
                ServiceState(
                    service_id="cart-service",
                    current_instances=4,
                    min_instances=1,
                    max_instances=10,
                    latency_ms=45.0,
                    max_latency_ms=200.0,
                    traffic_rpm=1500,
                    healthy=True,
                    state_version="v1",
                    cpu_utilization_percent=35.0,
                    memory_utilization_percent=45.0,
                    cost_per_hour=1.60,
                    service_type="web",
                    is_critical=False,
                ),
                ServiceState(
                    service_id="auth-service",
                    current_instances=3,
                    min_instances=2,
                    max_instances=8,
                    latency_ms=25.0,
                    max_latency_ms=100.0,
                    traffic_rpm=4500,
                    healthy=True,
                    state_version="v1",
                    cpu_utilization_percent=60.0,
                    memory_utilization_percent=55.0,
                    cost_per_hour=1.20,
                    service_type="web",
                    is_critical=True,
                ),
                ServiceState(
                    service_id="payment-gateway",
                    current_instances=5,
                    min_instances=3,
                    max_instances=12,
                    latency_ms=60.0,
                    max_latency_ms=150.0,
                    traffic_rpm=2200,
                    healthy=True,
                    state_version="v1",
                    cpu_utilization_percent=50.0,
                    memory_utilization_percent=40.0,
                    cost_per_hour=2.50,
                    service_type="api",
                    is_critical=True,
                ),
                ServiceState(
                    service_id="analytics-worker",
                    current_instances=2,
                    min_instances=0,
                    max_instances=6,
                    latency_ms=15.0,
                    max_latency_ms=500.0,
                    traffic_rpm=300,
                    healthy=True,
                    state_version="v1",
                    cpu_utilization_percent=20.0,
                    memory_utilization_percent=30.0,
                    cost_per_hour=0.80,
                    service_type="batch",
                    is_critical=False,
                ),
                ServiceState(
                    service_id="prod-db",
                    current_instances=2,
                    min_instances=2,
                    max_instances=4,
                    latency_ms=10.0,
                    max_latency_ms=50.0,
                    traffic_rpm=8000,
                    healthy=True,
                    state_version="v1",
                    cpu_utilization_percent=70.0,
                    memory_utilization_percent=80.0,
                    cost_per_hour=4.50,
                    service_type="database",
                    is_critical=True,
                ),
                ServiceState(
                    service_id="spiky-api",
                    current_instances=2,
                    min_instances=1,
                    max_instances=8,
                    latency_ms=120.0,
                    max_latency_ms=200.0,
                    traffic_rpm=1200,
                    healthy=True,
                    state_version="v1",
                    cpu_utilization_percent=60.0,
                    memory_utilization_percent=65.0,
                    cost_per_hour=0.90,
                    service_type="web",
                    is_critical=False,
                ),
            ],
        ),
        ScenarioType.IDLE_WASTE: SimulatorScenario(
            scenario_type=ScenarioType.IDLE_WASTE,
            name="Idle Cloud Waste & Overprovisioning",
            description="Severe cloud spend waste: cart-service overprovisioned with 6 instances at 4% CPU; analytics-worker idle at 0 RPM.",
            services=[
                ServiceState(
                    service_id="cart-service",
                    current_instances=6,
                    min_instances=1,
                    max_instances=10,
                    latency_ms=18.0,
                    max_latency_ms=200.0,
                    traffic_rpm=50,
                    healthy=True,
                    state_version="v1",
                    cpu_utilization_percent=4.0,
                    memory_utilization_percent=15.0,
                    cost_per_hour=2.40,
                    service_type="web",
                    is_critical=False,
                ),
                ServiceState(
                    service_id="analytics-worker",
                    current_instances=3,
                    min_instances=0,
                    max_instances=6,
                    latency_ms=10.0,
                    max_latency_ms=500.0,
                    traffic_rpm=0,
                    healthy=True,
                    state_version="v1",
                    cpu_utilization_percent=1.5,
                    memory_utilization_percent=8.0,
                    cost_per_hour=1.20,
                    service_type="batch",
                    is_critical=False,
                ),
            ],
        ),
        ScenarioType.TRAFFIC_SPIKE: SimulatorScenario(
            scenario_type=ScenarioType.TRAFFIC_SPIKE,
            name="High Traffic Surge & SLA Pressure",
            description="Flash sale surge pushing cart-service to 5000 RPM, 92% CPU, and 188ms latency near the 200ms SLA ceiling.",
            services=[
                ServiceState(
                    service_id="cart-service",
                    current_instances=2,
                    min_instances=1,
                    max_instances=10,
                    latency_ms=188.0,
                    max_latency_ms=200.0,
                    traffic_rpm=5000,
                    healthy=True,
                    state_version="v1",
                    cpu_utilization_percent=92.0,
                    memory_utilization_percent=85.0,
                    cost_per_hour=0.80,
                    service_type="web",
                    is_critical=False,
                ),
            ],
        ),
        ScenarioType.DEGRADATION: SimulatorScenario(
            scenario_type=ScenarioType.DEGRADATION,
            name="Service Outage / Degradation Incident",
            description="cart-service failing health checks (healthy=False) with elevated 450ms latency, testing emergency safety guardrails.",
            services=[
                ServiceState(
                    service_id="cart-service",
                    current_instances=3,
                    min_instances=1,
                    max_instances=10,
                    latency_ms=450.0,
                    max_latency_ms=200.0,
                    traffic_rpm=800,
                    healthy=False,
                    state_version="v1",
                    cpu_utilization_percent=98.0,
                    memory_utilization_percent=95.0,
                    cost_per_hour=1.20,
                    service_type="web",
                    is_critical=False,
                ),
            ],
        ),
        ScenarioType.PROTECTED_TARGET: SimulatorScenario(
            scenario_type=ScenarioType.PROTECTED_TARGET,
            name="Critical Infrastructure Protection",
            description="Primary database prod-db incurring high hourly spend during idle maintenance window, verifying safety locks prevent destructive actions.",
            services=[
                ServiceState(
                    service_id="prod-db",
                    current_instances=4,
                    min_instances=2,
                    max_instances=8,
                    latency_ms=8.0,
                    max_latency_ms=50.0,
                    traffic_rpm=0,
                    healthy=True,
                    state_version="v1",
                    cpu_utilization_percent=2.0,
                    memory_utilization_percent=30.0,
                    cost_per_hour=9.00,
                    service_type="database",
                    is_critical=True,
                ),
            ],
        ),
    }
