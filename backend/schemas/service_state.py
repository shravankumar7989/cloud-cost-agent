"""Service state model representing infrastructure state and capacity limits."""

from typing import Optional, Any
from pydantic import BaseModel, Field, model_validator

from backend.schemas.metrics import ServiceObservation


class ServiceState(BaseModel):
    """Represents the complete operational and capacity state of an infrastructure service.

    Attributes:
        service_id: Unique identifier or name of the service.
        current_instances: Current number of active instances.
        min_instances: Minimum allowable instances for the service.
        max_instances: Maximum allowable instances for the service.
        latency_ms: Current average or p99 latency in milliseconds.
        max_latency_ms: Maximum allowable latency threshold (SLA) in milliseconds.
        traffic_rpm: Current traffic in requests per minute.
        healthy: Whether the service is currently healthy and passing health checks.
        state_version: Unique version identifier for this state to detect stale data.
        cpu_utilization_percent: Optional CPU utilization percentage.
        memory_utilization_percent: Optional Memory utilization percentage.
        cost_per_hour: Optional estimated cost per hour.
        service_type: Optional classification (e.g. 'web', 'batch', 'database').
        is_critical: Optional flag designating a critical/protected service.
    """

    service_id: str = Field(..., description="Unique identifier or name of the service.")
    current_instances: int = Field(..., ge=0, description="Current number of active instances.")
    min_instances: int = Field(default=1, ge=0, description="Minimum allowable instances.")
    max_instances: int = Field(default=10, ge=1, description="Maximum allowable instances.")
    latency_ms: float = Field(..., ge=0.0, description="Current average or p99 latency in milliseconds.")
    max_latency_ms: float = Field(default=200.0, ge=0.0, description="Maximum allowable latency threshold (SLA) in milliseconds.")
    traffic_rpm: int = Field(default=0, ge=0, description="Traffic in requests per minute.")
    healthy: bool = Field(default=True, description="Whether the service is currently healthy.")
    state_version: str = Field(..., description="A unique version identifier for this state to detect stale data.")

    # Optional operational telemetry fields for compatibility and rich evaluation
    cpu_utilization_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0, description="CPU utilization percentage.")
    memory_utilization_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0, description="Memory utilization percentage.")
    cost_per_hour: Optional[float] = Field(default=None, ge=0.0, description="Current estimated cost per hour.")
    service_type: Optional[str] = Field(default=None, description="Type of service, e.g. 'batch', 'web_service', 'database'.")
    is_critical: bool = Field(default=False, description="Explicit flag designating a critical or non-automatable service.")

    @model_validator(mode="after")
    def validate_bounds(self) -> "ServiceState":
        """Validate relational constraints between min, max, and current instances."""
        if self.min_instances > self.max_instances:
            raise ValueError(
                f"min_instances ({self.min_instances}) cannot exceed max_instances ({self.max_instances})"
            )
        return self

    @classmethod
    def from_observation(
        cls,
        obs: ServiceObservation,
        current_instances: int = 1,
        min_instances: int = 1,
        max_instances: int = 10,
        max_latency_ms: float = 200.0,
        healthy: bool = True,
        service_type: Optional[str] = None,
        is_critical: bool = False,
    ) -> "ServiceState":
        """Factory method to construct a ServiceState from a raw ServiceObservation."""
        return cls(
            service_id=obs.service_id,
            current_instances=current_instances,
            min_instances=min_instances,
            max_instances=max_instances,
            latency_ms=obs.latency_ms,
            max_latency_ms=max_latency_ms,
            traffic_rpm=obs.traffic_rpm,
            healthy=healthy,
            state_version=obs.state_version,
            cpu_utilization_percent=obs.cpu_utilization_percent,
            memory_utilization_percent=obs.memory_utilization_percent,
            cost_per_hour=obs.cost_per_hour,
            service_type=service_type,
            is_critical=is_critical,
        )
