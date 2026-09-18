"""Deterministic Safety Engine.

This module provides deterministic safety validation for AI-proposed infrastructure
actions in cloud cost optimization. It evaluates action proposals strictly against
deterministic policies and telemetry observations without using an LLM.

Key Design Decisions:
- ServiceState represents the official infrastructure service state model.
- ServiceObservation is preserved untouched for backward compatibility.
- ExtendedServiceState and ServiceCapacity are preserved for backward compatibility.
- Explicit emergency policies govern actions on unhealthy services.
- Deterministic latency and instance constraints are enforced.
- Modular, testable functions validate each guardrail independently.
- Only proposal validation is performed; no cloud actions are executed here.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Iterable, List, Optional, Set, Tuple, Union

from pydantic import BaseModel, Field

from backend.schemas.actions import ActionProposal, InfrastructureAction
from backend.schemas.metrics import ServiceObservation
from backend.schemas.safety import SafetyCheckResult
from backend.schemas.service_state import ServiceState


class ServiceHealthStatus(str, Enum):
    """Health status classification for a service."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class EmergencyPolicy(str, Enum):
    """Explicitly documented emergency policies for degraded or unhealthy infrastructure.

    Emergency Policies:
    - NONE: Default operational policy. All mutating infrastructure actions (SCALE_DOWN,
      SCALE_UP, STOP_IDLE_SERVICE, RESIZE, DELAY_BATCH) are blocked on an unhealthy service
      to prevent escalating an active incident.
    - ALLOW_SCALE_UP: Authorizes emergency horizontal scaling on an unhealthy service
      to alleviate resource starvation/saturation (e.g. CPU/memory throttling causing health
      check failures). Destructive/reducing actions (SCALE_DOWN, STOP_IDLE_SERVICE, RESIZE)
      remain strictly blocked.
    """

    NONE = "none"
    ALLOW_SCALE_UP = "allow_scale_up"


class ServiceCapacity(BaseModel):
    """Optional operational capacity constraints for a service.

    Used when capacity limits (instance counts) are tracked separately
    from the raw telemetry observation.
    """

    current_instances: int = Field(default=1, ge=0, description="Current number of instances.")
    min_instances: int = Field(default=1, ge=0, description="Minimum allowable instances.")
    max_instances: int = Field(default=10, ge=1, description="Maximum allowable instances.")


class ExtendedServiceState(BaseModel):
    """Compatible extension encapsulating ServiceObservation with optional operational metadata.

    The baseline ServiceObservation does not contain instance counts or health status.
    This model allows orchestrators or simulator services to pass extended operational
    state without altering the shared teammate-owned ServiceObservation schema.
    """

    observation: ServiceObservation = Field(..., description="Baseline telemetry observation.")
    health_status: ServiceHealthStatus = Field(
        default=ServiceHealthStatus.HEALTHY, description="Current health status of the service."
    )
    capacity: Optional[ServiceCapacity] = Field(
        default=None, description="Optional capacity and scaling limits."
    )
    service_type: Optional[str] = Field(
        default=None,
        description="Type of service, e.g. 'batch', 'web_service', 'database', 'worker'.",
    )
    is_critical: bool = Field(
        default=False, description="Explicit flag designating a critical or non-automatable service."
    )


# ---------------------------------------------------------------------------
# Testable, Modular Safety Rule Functions
# ---------------------------------------------------------------------------

def validate_state_freshness(
    proposal_version: str, current_version: str
) -> Tuple[str, Optional[str]]:
    """Rule R01: Verify proposal state version matches current observation version."""
    rule_code = "R01_STALE_STATE"
    if proposal_version != current_version:
        reason = (
            f"Stale observation detected: proposal was based on state version '{proposal_version}', "
            f"but current state version is '{current_version}'."
        )
        return rule_code, reason
    return rule_code, None


def validate_service_identity(
    target_service_id: str,
    state_service_id: str,
    known_services: Optional[Set[str]] = None,
) -> Tuple[List[str], List[str]]:
    """Rules R02 & R14: Validate target service ID format, known registry status, and match."""
    applied_rules: List[str] = []
    rejection_reasons: List[str] = []

    normalized_target = target_service_id.strip().lower() if target_service_id else ""
    normalized_state = state_service_id.strip().lower() if state_service_id else ""

    # Rule R14: Check for empty, whitespace, or invalid service ID
    applied_rules.append("R14_UNKNOWN_SERVICE")
    if not normalized_target or normalized_target in ("unknown", "none"):
        rejection_reasons.append(
            f"Unknown service ID: target service ID '{target_service_id}' is invalid or unassigned."
        )
    elif known_services:
        normalized_known = {s.strip().lower() for s in known_services}
        if normalized_target not in normalized_known:
            rejection_reasons.append(
                f"Unknown service ID: target service '{target_service_id}' is not present in the known service catalog."
            )

    # Rule R02: Target service mismatch against state
    applied_rules.append("R02_TARGET_MISMATCH")
    if normalized_target != normalized_state:
        rejection_reasons.append(
            f"Target service mismatch: proposal targets '{target_service_id}', "
            f"but observation is for '{state_service_id}'."
        )

    return applied_rules, rejection_reasons


def validate_target_instance_counts(
    action: InfrastructureAction,
    current_instances: int,
    target_instances: Optional[int],
) -> Tuple[List[str], List[str]]:
    """Rule R15: Validate target instance count validity and directional logic."""
    applied_rules: List[str] = []
    rejection_reasons: List[str] = []

    if target_instances is None:
        return applied_rules, rejection_reasons

    applied_rules.append("R15_INVALID_TARGET_INSTANCES")

    if target_instances < 0:
        rejection_reasons.append(
            f"Invalid target instance count ({target_instances}): instance count cannot be negative."
        )
        return applied_rules, rejection_reasons

    if action == InfrastructureAction.SCALE_DOWN:
        if target_instances >= current_instances:
            rejection_reasons.append(
                f"Invalid target instance count ({target_instances}) for SCALE_DOWN: "
                f"target must be strictly less than current instances ({current_instances})."
            )
    elif action == InfrastructureAction.SCALE_UP:
        if target_instances <= current_instances:
            rejection_reasons.append(
                f"Invalid target instance count ({target_instances}) for SCALE_UP: "
                f"target must be strictly greater than current instances ({current_instances})."
            )

    return applied_rules, rejection_reasons


def validate_capacity_bounds(
    action: InfrastructureAction,
    current_instances: int,
    min_instances: int,
    max_instances: int,
    target_instances: Optional[int] = None,
) -> Tuple[List[str], List[str]]:
    """Rule R11: Enforce minimum floor for SCALE_DOWN and maximum ceiling for SCALE_UP."""
    applied_rules: List[str] = []
    rejection_reasons: List[str] = []

    if action == InfrastructureAction.SCALE_DOWN:
        applied_rules.append("R11_CAPACITY_FLOOR")
        if target_instances is not None:
            if target_instances < min_instances:
                rejection_reasons.append(
                    f"Cannot scale down: target instance count ({target_instances}) "
                    f"is below the minimum limit ({min_instances})."
                )
        else:
            if current_instances <= min_instances:
                rejection_reasons.append(
                    f"Cannot scale down: current instance count "
                    f"({current_instances}) is already at or below the minimum limit ({min_instances})."
                )
    elif action == InfrastructureAction.SCALE_UP:
        applied_rules.append("R11_CAPACITY_CEILING")
        if target_instances is not None:
            if target_instances > max_instances:
                rejection_reasons.append(
                    f"Cannot scale up: target instance count ({target_instances}) "
                    f"is already at or above maximum limit ({max_instances})."
                )
        else:
            if current_instances >= max_instances:
                rejection_reasons.append(
                    f"Cannot scale up: current instance count "
                    f"({current_instances}) is already at or above maximum limit ({max_instances})."
                )

    return applied_rules, rejection_reasons


def validate_service_health(
    action: InfrastructureAction,
    is_healthy: bool,
    health_status_value: str,
    emergency_policy: EmergencyPolicy = EmergencyPolicy.NONE,
) -> Tuple[List[str], List[str]]:
    """Rules R06 & R16: Reject actions when service is unhealthy unless documented emergency policy applies."""
    applied_rules: List[str] = []
    rejection_reasons: List[str] = []

    if is_healthy:
        return applied_rules, rejection_reasons

    applied_rules.append("R06_UNHEALTHY_SERVICE")

    # If action is NO_ACTION, it does not modify the unhealthy system
    if action == InfrastructureAction.NO_ACTION:
        return applied_rules, rejection_reasons

    # Check emergency policy
    if emergency_policy == EmergencyPolicy.ALLOW_SCALE_UP:
        applied_rules.append("R16_EMERGENCY_POLICY")
        if action == InfrastructureAction.SCALE_UP:
            # Explicitly permitted under emergency policy
            return applied_rules, rejection_reasons
        else:
            rejection_reasons.append(
                f"Service has non-healthy status '{health_status_value}'. "
                f"Action '{action.value}' is blocked during active degradation/outage. "
                f"Emergency policy '{emergency_policy.value}' permits only emergency SCALE_UP."
            )
            return applied_rules, rejection_reasons

    # Standard policy without emergency override: block disruptive/scaling actions
    if action in (
        InfrastructureAction.SCALE_DOWN,
        InfrastructureAction.STOP_IDLE_SERVICE,
        InfrastructureAction.RESIZE,
        InfrastructureAction.DELAY_BATCH,
        InfrastructureAction.SCALE_UP,
    ):
        rejection_reasons.append(
            f"Service has non-healthy status '{health_status_value}'. "
            f"Action '{action.value}' is blocked during active degradation/outage."
        )

    return applied_rules, rejection_reasons


def validate_latency_constraints(
    action: InfrastructureAction,
    latency_ms: float,
    max_latency_ms: float,
    current_instances: int,
    target_instances: Optional[int] = None,
    max_scale_down_latency_ms: float = 200.0,
) -> Tuple[List[str], List[str]]:
    """Rule R09: Deterministically evaluate latency constraints and projected latency for scale-down."""
    applied_rules: List[str] = []
    rejection_reasons: List[str] = []

    if action not in (InfrastructureAction.SCALE_DOWN, InfrastructureAction.RESIZE):
        return applied_rules, rejection_reasons

    applied_rules.append("R09_SCALE_DOWN_SLA_RISK")
    effective_ceiling = min(max_latency_ms, max_scale_down_latency_ms)

    # 1. Current latency SLA breach check
    if latency_ms > effective_ceiling:
        rejection_reasons.append(
            f"Scale down rejected due to SLA breach risk: current latency ({latency_ms:.1f}ms) "
            f"exceeds safe ceiling ({effective_ceiling:.1f}ms)."
        )
        return applied_rules, rejection_reasons

    # 2. Deterministic projected latency check:
    # If scaling down, estimate load increase assuming conserved traffic:
    # projected_latency = latency_ms * (current_instances / target_instances)
    target = target_instances if target_instances is not None else max(1, current_instances - 1)
    if current_instances > 1 and target < current_instances and target > 0 and latency_ms > 0:
        projected_latency = latency_ms * (current_instances / target)
        if projected_latency > effective_ceiling:
            rejection_reasons.append(
                f"Scale down rejected due to SLA breach risk: projected latency ({projected_latency:.1f}ms) "
                f"after scaling down from {current_instances} to {target} instances exceeds safe ceiling ({effective_ceiling:.1f}ms)."
            )

    return applied_rules, rejection_reasons


# ---------------------------------------------------------------------------
# Configuration & Context Models
# ---------------------------------------------------------------------------

@dataclass
class SafetyConfig:
    """Configurable thresholds for deterministic safety checks."""

    min_confidence: float = 0.70
    max_idle_cpu_percent: float = 5.0
    max_idle_memory_percent: float = 15.0
    max_idle_traffic_rpm: int = 0
    max_scale_down_latency_ms: float = 200.0
    max_scale_down_cpu_percent: float = 40.0
    max_scale_down_traffic_rpm: int = 1000
    cooldown_seconds: float = 300.0  # 5 minutes anti-flapping guard
    protected_services: Set[str] = field(
        default_factory=lambda: {
            "prod-db",
            "production-db",
            "auth-service",
            "primary-database",
            "payment-gateway",
        }
    )
    known_service_ids: Optional[Set[str]] = None
    default_emergency_policy: EmergencyPolicy = EmergencyPolicy.NONE


@dataclass
class SafetyContext:
    """Operational context for an evaluation run."""

    is_protected_override: Optional[bool] = None
    custom_protected_services: Optional[Set[str]] = None
    bypass_cooldown: bool = False
    now: Optional[datetime] = None
    emergency_policy: Optional[EmergencyPolicy] = None
    known_services_override: Optional[Set[str]] = None


# ---------------------------------------------------------------------------
# Deterministic Safety Engine
# ---------------------------------------------------------------------------

class DeterministicSafetyEngine:
    """Deterministic Safety Engine.

    Evaluates ActionProposal models against current telemetry and infrastructure service state.
    Strictly validates proposals deterministically without performing or claiming cloud execution.
    """

    def __init__(self, config: Optional[SafetyConfig] = None) -> None:
        self.config = config or SafetyConfig()
        # Track last executed action timestamp per service for anti-flapping
        self._last_action_times: Dict[str, datetime] = {}
        # Known service registry
        self._known_services: Set[str] = set()
        if self.config.known_service_ids:
            self._known_services.update(s.strip().lower() for s in self.config.known_service_ids)

    def register_service(self, service_id: str) -> None:
        """Register a known service ID in the engine's service catalog."""
        if service_id and service_id.strip():
            self._known_services.add(service_id.strip().lower())

    def register_services(self, service_ids: Iterable[str]) -> None:
        """Register multiple known service IDs."""
        for sid in service_ids:
            self.register_service(sid)

    def record_action_execution(
        self, service_id: str, timestamp: Optional[datetime] = None
    ) -> None:
        """Record an executed action timestamp for anti-flapping cooldown tracking."""
        ts = timestamp or datetime.now(timezone.utc)
        self._last_action_times[service_id.strip().lower()] = ts

    def clear_cooldown(self, service_id: Optional[str] = None) -> None:
        """Clear cooldown records for one service or all services."""
        if service_id is not None:
            self._last_action_times.pop(service_id.strip().lower(), None)
        else:
            self._last_action_times.clear()

    def is_in_cooldown(
        self, service_id: str, current_time: datetime
    ) -> Tuple[bool, float]:
        """Check if service is within cooldown window. Returns (is_cooling, elapsed_seconds)."""
        key = service_id.strip().lower()
        if key not in self._last_action_times:
            return False, 0.0

        last_time = self._last_action_times[key]
        if last_time.tzinfo is None and current_time.tzinfo is not None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        elif last_time.tzinfo is not None and current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        elapsed = (current_time - last_time).total_seconds()
        if elapsed < self.config.cooldown_seconds:
            return True, max(0.0, elapsed)
        return False, elapsed

    def is_service_protected(
        self,
        service_id: str,
        context: Optional[SafetyContext] = None,
        is_explicitly_critical: bool = False,
    ) -> bool:
        """Check if service is critical or protected from destructive changes."""
        if context and context.is_protected_override is not None:
            return context.is_protected_override

        if is_explicitly_critical:
            return True

        sid = service_id.strip().lower()
        if sid in self.config.protected_services:
            return True

        if context and context.custom_protected_services:
            normalized_custom = {s.strip().lower() for s in context.custom_protected_services}
            if sid in normalized_custom:
                return True

        # Heuristic checks for critical infrastructure markers
        critical_markers = ["prod-db", "production-db", "payment", "auth", "core-db"]
        if any(marker in sid for marker in critical_markers):
            return True

        return False

    def evaluate(
        self,
        proposal: ActionProposal,
        current_state: Union[ServiceState, ServiceObservation, ExtendedServiceState],
        context: Optional[SafetyContext] = None,
    ) -> SafetyCheckResult:
        """Evaluate an ActionProposal against current telemetry and operational state.

        Args:
            proposal: The ActionProposal proposed by the LLM Decision Agent.
            current_state: Current ServiceState, ServiceObservation, or ExtendedServiceState.
            context: Optional SafetyContext for overrides, custom time, emergency policy, or bypasses.

        Returns:
            SafetyCheckResult containing boolean approval, version audits,
            applied rules, and explicit rejection reasons.
        """
        # Unpack state representations into canonical variables
        has_capacity_model = False
        if isinstance(current_state, ServiceState):
            service_id = current_state.service_id
            state_version = current_state.state_version
            current_instances = current_state.current_instances
            min_instances = current_state.min_instances
            max_instances = current_state.max_instances
            latency_ms = current_state.latency_ms
            max_latency_ms = current_state.max_latency_ms
            traffic_rpm = current_state.traffic_rpm
            is_healthy = current_state.healthy
            health_status_val = "healthy" if is_healthy else "unhealthy"
            cpu_percent = current_state.cpu_utilization_percent
            memory_percent = current_state.memory_utilization_percent
            service_type = current_state.service_type
            is_explicitly_critical = current_state.is_critical
            has_capacity_model = True
        elif isinstance(current_state, ExtendedServiceState):
            obs = current_state.observation
            service_id = obs.service_id
            state_version = obs.state_version
            cap = current_state.capacity or ServiceCapacity(
                current_instances=1, min_instances=1, max_instances=10
            )
            has_capacity_model = current_state.capacity is not None
            current_instances = cap.current_instances
            min_instances = cap.min_instances
            max_instances = cap.max_instances
            latency_ms = obs.latency_ms
            max_latency_ms = self.config.max_scale_down_latency_ms
            traffic_rpm = obs.traffic_rpm
            is_healthy = current_state.health_status == ServiceHealthStatus.HEALTHY
            health_status_val = current_state.health_status.value
            cpu_percent = obs.cpu_utilization_percent
            memory_percent = obs.memory_utilization_percent
            service_type = current_state.service_type
            is_explicitly_critical = current_state.is_critical
        else:
            # Baseline ServiceObservation
            obs = current_state
            service_id = obs.service_id
            state_version = obs.state_version
            current_instances = 1
            min_instances = 1
            max_instances = 10
            latency_ms = obs.latency_ms
            max_latency_ms = self.config.max_scale_down_latency_ms
            traffic_rpm = obs.traffic_rpm
            is_healthy = True
            health_status_val = "healthy"
            cpu_percent = obs.cpu_utilization_percent
            memory_percent = obs.memory_utilization_percent
            service_type = None
            is_explicitly_critical = False
            has_capacity_model = False

        applied_rules: List[str] = []
        rejection_reasons: List[str] = []

        now = context.now if context and context.now else datetime.now(timezone.utc)

        # Emergency policy resolution
        emergency_policy = (
            context.emergency_policy
            if context and context.emergency_policy is not None
            else self.config.default_emergency_policy
        )

        # Active known services resolution
        known_services: Optional[Set[str]] = None
        if context and context.known_services_override is not None:
            known_services = context.known_services_override
        elif self._known_services:
            known_services = self._known_services

        # Target instances from proposal
        target_instances = getattr(proposal, "target_instances", None)

        # -------------------------------------------------------------------
        # Rule R01: Stale Observation Check
        # -------------------------------------------------------------------
        r01_code, r01_reason = validate_state_freshness(
            proposal.observation_version, state_version
        )
        applied_rules.append(r01_code)
        if r01_reason:
            rejection_reasons.append(r01_reason)

        # -------------------------------------------------------------------
        # Rules R02 & R14: Target Service Identity & Unknown Service ID Check
        # -------------------------------------------------------------------
        r_id_codes, r_id_reasons = validate_service_identity(
            proposal.target_service_id, service_id, known_services=known_services
        )
        applied_rules.extend(r_id_codes)
        rejection_reasons.extend(r_id_reasons)

        # -------------------------------------------------------------------
        # Rule R03: Validate Supported Infrastructure Action
        # -------------------------------------------------------------------
        applied_rules.append("R03_ACTION_SUPPORTED")
        if not isinstance(proposal.action, InfrastructureAction):
            try:
                proposal_action = InfrastructureAction(proposal.action)
            except ValueError:
                rejection_reasons.append(
                    f"Unsupported action: '{proposal.action}' is not a recognized InfrastructureAction."
                )
                return SafetyCheckResult(
                    is_approved=False,
                    proposal_version=proposal.observation_version,
                    evaluated_against_version=state_version,
                    rejection_reasons=rejection_reasons,
                    applied_rules=applied_rules,
                )
        else:
            proposal_action = proposal.action

        # -------------------------------------------------------------------
        # Rule R04: Handle NO_ACTION safely
        # -------------------------------------------------------------------
        if proposal_action == InfrastructureAction.NO_ACTION:
            applied_rules.append("R04_NO_ACTION_SAFE")
            is_approved = len(rejection_reasons) == 0
            return SafetyCheckResult(
                is_approved=is_approved,
                proposal_version=proposal.observation_version,
                evaluated_against_version=state_version,
                rejection_reasons=rejection_reasons,
                applied_rules=applied_rules,
            )

        # -------------------------------------------------------------------
        # Rule R05: Confidence Floor Check
        # -------------------------------------------------------------------
        applied_rules.append("R05_LOW_CONFIDENCE")
        if proposal.confidence < self.config.min_confidence:
            rejection_reasons.append(
                f"Proposal confidence ({proposal.confidence:.2f}) is below the required "
                f"minimum threshold ({self.config.min_confidence:.2f})."
            )

        # -------------------------------------------------------------------
        # Rule R06 & R16: Health Check and Emergency Policy
        # -------------------------------------------------------------------
        health_codes, health_reasons = validate_service_health(
            proposal_action,
            is_healthy,
            health_status_val,
            emergency_policy=emergency_policy,
        )
        applied_rules.extend(health_codes)
        rejection_reasons.extend(health_reasons)

        # -------------------------------------------------------------------
        # Rule R15: Validate Target Instance Counts
        # -------------------------------------------------------------------
        t_codes, t_reasons = validate_target_instance_counts(
            proposal_action, current_instances, target_instances
        )
        applied_rules.extend(t_codes)
        rejection_reasons.extend(t_reasons)

        # -------------------------------------------------------------------
        # Rule R07: Protected Service Guard
        # -------------------------------------------------------------------
        is_protected = self.is_service_protected(
            service_id, context=context, is_explicitly_critical=is_explicitly_critical
        )
        if proposal_action in (InfrastructureAction.STOP_IDLE_SERVICE, InfrastructureAction.RESIZE):
            applied_rules.append("R07_PROTECTED_SERVICE")
            if is_protected:
                rejection_reasons.append(
                    f"Service '{service_id}' is designated as protected/critical. "
                    f"Action '{proposal_action.value}' cannot be executed automatically."
                )

        # -------------------------------------------------------------------
        # Rule R08: Stop Active Service Guard (STOP_IDLE_SERVICE)
        # -------------------------------------------------------------------
        if proposal_action == InfrastructureAction.STOP_IDLE_SERVICE:
            applied_rules.append("R08_STOP_ACTIVE_SERVICE")
            if traffic_rpm > self.config.max_idle_traffic_rpm:
                rejection_reasons.append(
                    f"Cannot stop active service: active traffic detected ({traffic_rpm} RPM > "
                    f"{self.config.max_idle_traffic_rpm} RPM threshold)."
                )
            if cpu_percent is not None and cpu_percent > self.config.max_idle_cpu_percent:
                rejection_reasons.append(
                    f"Cannot stop active service: CPU utilization is {cpu_percent:.1f}% "
                    f"(maximum idle threshold is {self.config.max_idle_cpu_percent:.1f}%)."
                )
            if memory_percent is not None and memory_percent > self.config.max_idle_memory_percent:
                rejection_reasons.append(
                    f"Cannot stop active service: Memory utilization is {memory_percent:.1f}% "
                    f"(maximum idle threshold is {self.config.max_idle_memory_percent:.1f}%)."
                )
            if has_capacity_model and min_instances > 0:
                rejection_reasons.append(
                    f"Cannot stop service: minimum instance constraint is {min_instances} "
                    f"(service must maintain at least {min_instances} running instance(s))."
                )

        # -------------------------------------------------------------------
        # Rule R09: Latency Constraints & Deterministic SLA Risk (SCALE_DOWN, RESIZE)
        # -------------------------------------------------------------------
        lat_codes, lat_reasons = validate_latency_constraints(
            proposal_action,
            latency_ms=latency_ms,
            max_latency_ms=max_latency_ms,
            current_instances=current_instances,
            target_instances=target_instances,
            max_scale_down_latency_ms=self.config.max_scale_down_latency_ms,
        )
        applied_rules.extend(lat_codes)
        rejection_reasons.extend(lat_reasons)

        if proposal_action in (InfrastructureAction.SCALE_DOWN, InfrastructureAction.RESIZE):
            if cpu_percent is not None and cpu_percent > self.config.max_scale_down_cpu_percent:
                rejection_reasons.append(
                    f"Scale down rejected due to capacity risk: CPU utilization is {cpu_percent:.1f}% "
                    f"(maximum safe scale down ceiling is {self.config.max_scale_down_cpu_percent:.1f}%)."
                )

        # -------------------------------------------------------------------
        # Rule R10: Traffic Surge Guard (SCALE_DOWN)
        # -------------------------------------------------------------------
        if proposal_action == InfrastructureAction.SCALE_DOWN:
            applied_rules.append("R10_TRAFFIC_SURGE_GUARD")
            if traffic_rpm > self.config.max_scale_down_traffic_rpm:
                rejection_reasons.append(
                    f"Scale down rejected due to elevated traffic: current traffic ({traffic_rpm} RPM) "
                    f"exceeds scale-down traffic limit ({self.config.max_scale_down_traffic_rpm} RPM)."
                )

        # -------------------------------------------------------------------
        # Rule R11: Capacity Instance Floor & Ceiling Bounds (SCALE_DOWN, SCALE_UP)
        # -------------------------------------------------------------------
        if has_capacity_model:
            cap_codes, cap_reasons = validate_capacity_bounds(
                proposal_action,
                current_instances=current_instances,
                min_instances=min_instances,
                max_instances=max_instances,
                target_instances=target_instances,
            )
            # Re-format reason for R11_CAPACITY_FLOOR / CEILING to maintain backward compatibility with tests
            applied_rules.extend(cap_codes)
            if proposal_action == InfrastructureAction.SCALE_DOWN and cap_reasons:
                rejection_reasons.append(
                    f"Cannot scale down service '{service_id}': current instance count "
                    f"({current_instances}) is already at or below the minimum limit ({min_instances})."
                    if target_instances is None
                    else f"Cannot scale down service '{service_id}': target instance count "
                    f"({target_instances}) is below the minimum limit ({min_instances})."
                )
            elif proposal_action == InfrastructureAction.SCALE_UP and cap_reasons:
                rejection_reasons.append(
                    f"Cannot scale up service '{service_id}': current instance count "
                    f"({current_instances}) is already at or above maximum limit ({max_instances})."
                    if target_instances is None
                    else f"Cannot scale up service '{service_id}': target instance count "
                    f"({target_instances}) is already at or above maximum limit ({max_instances})."
                )

        # -------------------------------------------------------------------
        # Rule R12: Workload Suitability Guard (DELAY_BATCH)
        # -------------------------------------------------------------------
        if proposal_action == InfrastructureAction.DELAY_BATCH:
            applied_rules.append("R12_WORKLOAD_SUITABILITY")
            if service_type and service_type.strip().lower() in ("web", "web_service", "api", "gateway"):
                rejection_reasons.append(
                    f"Cannot apply 'delay_batch' to real-time service '{service_id}' "
                    f"(service type is '{service_type}')."
                )

        # -------------------------------------------------------------------
        # Rule R13: Anti-flapping Cooldown Check
        # -------------------------------------------------------------------
        should_check_cooldown = not (context and context.bypass_cooldown)
        if should_check_cooldown:
            applied_rules.append("R13_ACTION_COOLDOWN")
            is_cooling, elapsed = self.is_in_cooldown(service_id, now)
            if is_cooling:
                remaining = self.config.cooldown_seconds - elapsed
                rejection_reasons.append(
                    f"Service '{service_id}' is in cooldown. "
                    f"Elapsed: {elapsed:.1f}s, Remaining: {remaining:.1f}s "
                    f"(Cooldown requirement: {self.config.cooldown_seconds:.1f}s)."
                )

        is_approved = len(rejection_reasons) == 0

        return SafetyCheckResult(
            is_approved=is_approved,
            proposal_version=proposal.observation_version,
            evaluated_against_version=state_version,
            rejection_reasons=rejection_reasons,
            applied_rules=applied_rules,
        )
