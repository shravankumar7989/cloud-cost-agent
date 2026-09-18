"""Simulator API endpoints for controlling cloud environment dynamics and scenarios."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.api.deps import get_simulator
from backend.schemas.service_state import ServiceState
from backend.services.state_manager import ServiceNotFoundError
from backend.simulator.cloud_simulator import CloudEnvironmentSimulator
from backend.simulator.scenarios import ScenarioType, get_scenario_definitions

router = APIRouter(prefix="/simulator", tags=["Simulator"])


class TickRequest(BaseModel):
    """Payload for advancing the simulator clock."""

    elapsed_seconds: float = Field(60.0, ge=1.0, le=86400.0)


class TrafficSpikeRequest(BaseModel):
    """Payload for injecting a traffic surge."""

    service_id: str
    multiplier: float = Field(3.0, ge=1.1, le=20.0)


class ServiceTargetRequest(BaseModel):
    """Target service payload."""

    service_id: str


@router.get("/status", response_model=Dict[str, Any])
def get_simulator_status(
    simulator: CloudEnvironmentSimulator = Depends(get_simulator),
) -> Dict[str, Any]:
    """Retrieve active scenario, simulation clock, and telemetry overview."""
    return simulator.get_status()


@router.get("/scenarios", response_model=Dict[str, Any])
def list_scenarios() -> Dict[str, Any]:
    """List all available demo scenarios with descriptions."""
    scenarios = get_scenario_definitions()
    return {
        s_type.value: {
            "name": s_def.name,
            "description": s_def.description,
            "service_count": len(s_def.services),
            "services": [svc.service_id for svc in s_def.services],
        }
        for s_type, s_def in scenarios.items()
    }


@router.post("/scenario/{scenario_name}", response_model=List[ServiceState])
def load_scenario(
    scenario_name: str,
    simulator: CloudEnvironmentSimulator = Depends(get_simulator),
) -> List[ServiceState]:
    """Switch active simulation scenario."""
    try:
        scenario_type = ScenarioType(scenario_name.lower())
    except ValueError:
        valid_options = [s.value for s in ScenarioType]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scenario '{scenario_name}'. Valid options: {valid_options}",
        )

    return simulator.load_scenario(scenario_type)


@router.post("/tick", response_model=List[ServiceState])
def advance_tick(
    req: TickRequest = TickRequest(),
    simulator: CloudEnvironmentSimulator = Depends(get_simulator),
) -> List[ServiceState]:
    """Advance simulation time and recalculate workload telemetry."""
    return simulator.tick(elapsed_seconds=req.elapsed_seconds)


@router.post("/inject/spike", response_model=ServiceState)
def inject_traffic_spike(
    req: TrafficSpikeRequest,
    simulator: CloudEnvironmentSimulator = Depends(get_simulator),
) -> ServiceState:
    """Surge traffic on a service to test scaling response and SLA protection."""
    try:
        return simulator.inject_traffic_spike(req.service_id, multiplier=req.multiplier)
    except ServiceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{req.service_id}' was not found.",
        )


@router.post("/inject/degradation", response_model=ServiceState)
def inject_degradation(
    req: ServiceTargetRequest,
    simulator: CloudEnvironmentSimulator = Depends(get_simulator),
) -> ServiceState:
    """Inject a health check failure to test emergency safety policies."""
    try:
        return simulator.inject_degradation(req.service_id)
    except ServiceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{req.service_id}' was not found.",
        )


@router.post("/inject/restore", response_model=ServiceState)
def restore_health(
    req: ServiceTargetRequest,
    simulator: CloudEnvironmentSimulator = Depends(get_simulator),
) -> ServiceState:
    """Restore a service to healthy status."""
    try:
        return simulator.restore_health(req.service_id)
    except ServiceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{req.service_id}' was not found.",
        )
