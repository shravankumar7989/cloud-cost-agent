"""Cloud Environment Simulator.

Simulates dynamic cloud telemetry, workload physics, fault injections,
and demo scenarios for testing cloud-cost optimization agents.
"""

from math import sin
from threading import RLock
from typing import Any, Dict, List, Optional

from backend.schemas.service_state import ServiceState
from backend.services.state_manager import ServiceNotFoundError, ServiceStateManager
from backend.simulator.scenarios import (
    ScenarioType,
    get_scenario_definitions,
)


class CloudEnvironmentSimulator:
    """Simulator modeling cloud infrastructure dynamics, telemetry, and scenarios."""

    def __init__(self, state_manager: ServiceStateManager) -> None:
        self.state_manager = state_manager
        self._lock = RLock()
        self.active_scenario: ScenarioType = ScenarioType.NORMAL
        self.tick_count: int = 0
        self.total_simulated_seconds: float = 0.0

    def load_scenario(self, scenario_type: ScenarioType) -> List[ServiceState]:
        """Load a predefined demo scenario into the service state manager.

        Args:
            scenario_type: Target ScenarioType to load.

        Returns:
            List of registered ServiceState instances for the scenario.
        """
        scenarios = get_scenario_definitions()
        if scenario_type not in scenarios:
            raise ValueError(f"Unknown scenario type: '{scenario_type}'")

        scenario = scenarios[scenario_type]

        with self._lock:
            self.state_manager.reset()
            # First seed default catalog if specialized scenario has a subset
            if scenario_type != ScenarioType.NORMAL:
                self.state_manager.seed_default_services()

            # Overwrite/register the scenario-specific states
            for svc in scenario.services:
                self.state_manager.register_service(svc, allow_overwrite=True)

            self.active_scenario = scenario_type
            self.tick_count = 0
            self.total_simulated_seconds = 0.0
            return self.state_manager.list_services()

    def tick(self, elapsed_seconds: float = 60.0) -> List[ServiceState]:
        """Advance the simulation by elapsed_seconds and recompute telemetry physics.

        Physics rules:
        - Diurnal traffic cycle: gentle deterministic wave using sine of tick count.
        - Load per instance: CPU% scales proportionally with (traffic / current_instances).
        - Latency: Increases non-linearly if CPU utilization exceeds 75%.
        - Stopped services (0 instances) stay at 0 RPM, 0% CPU, and $0.00 spend.

        Args:
            elapsed_seconds: Number of seconds to advance.

        Returns:
            List of updated ServiceState instances.
        """
        with self._lock:
            self.tick_count += 1
            self.total_simulated_seconds += elapsed_seconds

            services = self.state_manager.list_services()
            updated_services: List[ServiceState] = []

            for svc in services:
                sid = svc.service_id

                # Stopped service maintains zero load and zero cost
                if svc.current_instances <= 0:
                    updated = self.state_manager.update_metrics(
                        service_id=sid,
                        traffic_rpm=0,
                        cpu_utilization_percent=0.0,
                        memory_utilization_percent=0.0,
                        latency_ms=0.0,
                        cost_per_hour=0.0,
                        bump_version=False,
                    )
                    updated_services.append(updated)
                    continue

                # Normal running service: apply workload dynamics
                # 1. Deterministic traffic oscillation (+/- 5%)
                wave = sin(self.tick_count * 0.2)
                base_traffic = max(0, svc.traffic_rpm)
                traffic_adjustment = int(base_traffic * (1.0 + (0.05 * wave)))
                new_traffic = max(0, traffic_adjustment)

                # 2. CPU load per instance
                # Baseline traffic per instance is ~300 RPM for 30% CPU
                traffic_per_inst = new_traffic / svc.current_instances
                calculated_cpu = round(min(100.0, max(2.0, traffic_per_inst * 0.10)), 1)

                # 3. Latency curve: base latency + queueing overhead if high CPU
                base_latency = max(5.0, svc.latency_ms)
                if calculated_cpu > 75.0:
                    overhead_factor = 1.0 + ((calculated_cpu - 75.0) / 25.0)
                    new_latency = round(min(500.0, base_latency * overhead_factor), 1)
                else:
                    new_latency = round(max(5.0, base_latency * 0.98), 1)

                # 4. Hourly cost based on active instances ($0.40 unit cost per instance)
                unit_cost = (svc.cost_per_hour / svc.current_instances) if (svc.cost_per_hour and svc.current_instances > 0) else 0.40
                new_cost = round(unit_cost * svc.current_instances, 2)

                # Memory utilization tracks CPU with lower volatility
                curr_mem = svc.memory_utilization_percent or 40.0
                new_mem = round(min(98.0, max(10.0, (curr_mem * 0.9) + (calculated_cpu * 0.1))), 1)

                updated = self.state_manager.update_metrics(
                    service_id=sid,
                    traffic_rpm=new_traffic,
                    cpu_utilization_percent=calculated_cpu,
                    memory_utilization_percent=new_mem,
                    latency_ms=new_latency,
                    cost_per_hour=new_cost,
                    bump_version=True,
                )
                updated_services.append(updated)

            return updated_services

    def inject_traffic_spike(
        self, service_id: str, multiplier: float = 3.0
    ) -> ServiceState:
        """Inject an immediate traffic spike on a service.

        Args:
            service_id: The target service ID.
            multiplier: Factor by which to multiply traffic.

        Returns:
            The modified ServiceState.
        """
        with self._lock:
            state = self.state_manager.get_service(service_id)
            if not state:
                raise ServiceNotFoundError(f"Service '{service_id}' was not found.")

            base_traffic = max(500, state.traffic_rpm)
            spiked_traffic = int(base_traffic * multiplier)
            inst = max(1, state.current_instances)
            spiked_cpu = min(98.0, round(spiked_traffic / inst * 0.12, 1))
            spiked_latency = min(350.0, round(state.latency_ms * 2.2, 1))

            return self.state_manager.update_metrics(
                service_id=service_id,
                traffic_rpm=spiked_traffic,
                cpu_utilization_percent=spiked_cpu,
                latency_ms=spiked_latency,
                bump_version=True,
            )

    def inject_degradation(self, service_id: str) -> ServiceState:
        """Inject a service health check degradation incident.

        Args:
            service_id: Target service ID.

        Returns:
            The modified ServiceState with healthy=False.
        """
        with self._lock:
            state = self.state_manager.get_service(service_id)
            if not state:
                raise ServiceNotFoundError(f"Service '{service_id}' was not found.")

            inflated_latency = max(350.0, state.latency_ms * 3.0)
            return self.state_manager.update_metrics(
                service_id=service_id,
                healthy=False,
                latency_ms=round(inflated_latency, 1),
                bump_version=True,
            )

    def restore_health(self, service_id: str) -> ServiceState:
        """Restore a service to healthy status with normal latency.

        Args:
            service_id: Target service ID.

        Returns:
            The restored ServiceState.
        """
        with self._lock:
            state = self.state_manager.get_service(service_id)
            if not state:
                raise ServiceNotFoundError(f"Service '{service_id}' was not found.")

            normal_latency = min(state.max_latency_ms * 0.5, 45.0)
            return self.state_manager.update_metrics(
                service_id=service_id,
                healthy=True,
                latency_ms=normal_latency,
                bump_version=True,
            )

    def get_status(self) -> Dict[str, Any]:
        """Retrieve overall simulation status and active service metrics."""
        with self._lock:
            services = self.state_manager.list_services()
            return {
                "active_scenario": self.active_scenario.value,
                "tick_count": self.tick_count,
                "total_simulated_seconds": self.total_simulated_seconds,
                "service_count": len(services),
                "services": [
                    {
                        "service_id": s.service_id,
                        "instances": s.current_instances,
                        "healthy": s.healthy,
                        "traffic_rpm": s.traffic_rpm,
                        "cpu_percent": s.cpu_utilization_percent,
                        "latency_ms": s.latency_ms,
                        "cost_per_hour": s.cost_per_hour,
                        "state_version": s.state_version,
                    }
                    for s in services
                ],
            }
