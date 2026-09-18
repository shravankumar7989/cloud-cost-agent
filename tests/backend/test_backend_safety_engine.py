"""Unit tests for the Deterministic Safety Engine under tests/backend/.

Verifies all deterministic validation requirements:
1. Deterministic validation (non-LLM).
2. Stale proposal rejection (version mismatch).
3. Target service mismatch rejection.
4. Safe handling of NO_ACTION.
5. Rules for unsupported or unsafe actions (SLA breach, active traffic, critical service).
6. Non-assumption of instance counts/health on raw ServiceObservation.
7. ExtendedServiceState and ServiceCapacity handling for instance limits and health.
8. Output conforms to SafetyCheckResult and never claims execution.
"""

from datetime import datetime, timedelta, timezone
import pytest

from backend.schemas.actions import ActionProposal, InfrastructureAction
from backend.schemas.metrics import ServiceObservation
from backend.schemas.safety import SafetyCheckResult
from backend.schemas.service_state import ServiceState
from backend.services.safety_engine import (
    DeterministicSafetyEngine,
    EmergencyPolicy,
    ExtendedServiceState,
    SafetyConfig,
    SafetyContext,
    ServiceCapacity,
    ServiceHealthStatus,
    validate_capacity_bounds,
    validate_latency_constraints,
    validate_service_health,
    validate_service_identity,
    validate_state_freshness,
    validate_target_instance_counts,
)



@pytest.fixture
def engine() -> DeterministicSafetyEngine:
    return DeterministicSafetyEngine()


@pytest.fixture
def baseline_observation() -> ServiceObservation:
    """Standard ServiceObservation without assuming instance counts or health status."""
    return ServiceObservation(
        service_id="report-worker",
        cpu_utilization_percent=3.5,
        memory_utilization_percent=10.0,
        traffic_rpm=0,
        latency_ms=45.0,
        cost_per_hour=1.20,
        observation_timestamp=datetime.now(timezone.utc),
        state_version="state-v100",
    )


@pytest.fixture
def valid_idle_proposal() -> ActionProposal:
    return ActionProposal(
        action=InfrastructureAction.STOP_IDLE_SERVICE,
        target_service_id="report-worker",
        reason="Service has 0 RPM traffic and minimal CPU utilization for 30 minutes.",
        expected_effect="Eliminate hourly cost while preserving data integrity.",
        observation_version="state-v100",
        confidence=0.92,
    )


class TestDeterministicSafetyEngine:
    """Test suite for deterministic safety rules."""

    # 1. Output Contract & Pure Validation
    def test_result_conforms_to_schema_without_execution(
        self, engine: DeterministicSafetyEngine, baseline_observation: ServiceObservation, valid_idle_proposal: ActionProposal
    ):
        """Engine must return a pure SafetyCheckResult and not execute actions."""
        result = engine.evaluate(valid_idle_proposal, baseline_observation)

        assert isinstance(result, SafetyCheckResult)
        assert hasattr(result, "is_approved")
        assert hasattr(result, "proposal_version")
        assert hasattr(result, "evaluated_against_version")
        assert hasattr(result, "rejection_reasons")
        assert hasattr(result, "applied_rules")
        # Ensure it does not include execution-only fields
        assert not hasattr(result, "status")
        assert not hasattr(result, "new_state_version")

    # 2. Stale Proposal Rejection
    def test_stale_proposal_version_rejected(
        self, engine: DeterministicSafetyEngine, baseline_observation: ServiceObservation
    ):
        """Proposal based on outdated state version must be rejected."""
        stale_proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="payment-worker",
            reason="Scale down cluster",
            expected_effect="Save cost",
            observation_version="state-v090",  # Differs from state-v100
            confidence=0.95,
        )

        result = engine.evaluate(stale_proposal, baseline_observation)

        assert not result.is_approved
        assert "R01_STALE_STATE" in result.applied_rules
        assert result.proposal_version == "state-v090"
        assert result.evaluated_against_version == "state-v100"
        assert any("Stale observation detected" in r for r in result.rejection_reasons)

    # 3. Target Service ID Validation
    def test_target_service_mismatch_rejected(
        self, engine: DeterministicSafetyEngine, baseline_observation: ServiceObservation
    ):
        """Proposal targeting a different service ID must be rejected."""
        mismatched_proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="inventory-worker",  # Does not match payment-worker
            reason="Scale down cluster",
            expected_effect="Save cost",
            observation_version="state-v100",
            confidence=0.88,
        )

        result = engine.evaluate(mismatched_proposal, baseline_observation)

        assert not result.is_approved
        assert "R02_TARGET_MISMATCH" in result.applied_rules
        assert any("Target service mismatch" in r for r in result.rejection_reasons)

    # 4. Safe Handling of NO_ACTION
    def test_no_action_approved_when_version_matches(
        self, engine: DeterministicSafetyEngine, baseline_observation: ServiceObservation
    ):
        """NO_ACTION is safe and approved when state versions match."""
        no_action_proposal = ActionProposal(
            action=InfrastructureAction.NO_ACTION,
            target_service_id="report-worker",
            reason="Metrics are nominal; no intervention required.",
            expected_effect="Maintain current stable configuration.",
            observation_version="state-v100",
            confidence=0.50,  # Low confidence should NOT block NO_ACTION
        )

        result = engine.evaluate(no_action_proposal, baseline_observation)

        assert result.is_approved
        assert "R04_NO_ACTION_SAFE" in result.applied_rules
        assert len(result.rejection_reasons) == 0

    def test_no_action_rejected_if_stale_or_mismatched(
        self, engine: DeterministicSafetyEngine, baseline_observation: ServiceObservation
    ):
        """NO_ACTION must still be rejected if stale state or mismatched target."""
        stale_no_action = ActionProposal(
            action=InfrastructureAction.NO_ACTION,
            target_service_id="report-worker",
            reason="Nominal",
            expected_effect="Maintain",
            observation_version="stale-v5",
            confidence=0.99,
        )

        result = engine.evaluate(stale_no_action, baseline_observation)

        assert not result.is_approved
        assert any("Stale observation" in r for r in result.rejection_reasons)

    # 5. Low Confidence Rejection
    def test_low_confidence_proposal_rejected(
        self, engine: DeterministicSafetyEngine, baseline_observation: ServiceObservation
    ):
        """Proposals with confidence < min_confidence (0.70) must be rejected."""
        low_conf_proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="report-worker",
            reason="Guessing that we can scale down",
            expected_effect="Unclear",
            observation_version="state-v100",
            confidence=0.52,
        )

        result = engine.evaluate(low_conf_proposal, baseline_observation)

        assert not result.is_approved
        assert "R05_LOW_CONFIDENCE" in result.applied_rules
        assert any("Proposal confidence" in r for r in result.rejection_reasons)

    # 6. STOP_IDLE_SERVICE Validation Rules
    def test_stop_idle_service_approved_for_truly_idle(
        self, engine: DeterministicSafetyEngine, baseline_observation: ServiceObservation, valid_idle_proposal: ActionProposal
    ):
        """Stopping an idle service with 0 RPM and low CPU/mem is approved."""
        result = engine.evaluate(valid_idle_proposal, baseline_observation)

        assert result.is_approved
        assert "R08_STOP_ACTIVE_SERVICE" in result.applied_rules
        assert len(result.rejection_reasons) == 0

    def test_stop_idle_service_rejected_if_traffic_present(
        self, engine: DeterministicSafetyEngine, valid_idle_proposal: ActionProposal
    ):
        """Cannot stop service if traffic_rpm > 0."""
        obs = ServiceObservation(
            service_id="payment-worker",
            cpu_utilization_percent=2.0,
            memory_utilization_percent=5.0,
            traffic_rpm=15,  # Active traffic
            latency_ms=30.0,
            cost_per_hour=1.0,
            observation_timestamp=datetime.now(timezone.utc),
            state_version="state-v100",
        )

        result = engine.evaluate(valid_idle_proposal, obs)

        assert not result.is_approved
        assert any("active traffic detected" in r for r in result.rejection_reasons)

    def test_stop_idle_service_rejected_if_cpu_high(
        self, engine: DeterministicSafetyEngine, valid_idle_proposal: ActionProposal
    ):
        """Cannot stop service if CPU > 5.0%."""
        obs = ServiceObservation(
            service_id="payment-worker",
            cpu_utilization_percent=18.5,  # Non-idle CPU
            memory_utilization_percent=5.0,
            traffic_rpm=0,
            latency_ms=30.0,
            cost_per_hour=1.0,
            observation_timestamp=datetime.now(timezone.utc),
            state_version="state-v100",
        )

        result = engine.evaluate(valid_idle_proposal, obs)

        assert not result.is_approved
        assert any("CPU utilization is 18.5%" in r for r in result.rejection_reasons)

    # 7. Critical / Protected Service Protection
    def test_stop_protected_service_rejected(self, engine: DeterministicSafetyEngine):
        """Critical database or auth service cannot be stopped automatically."""
        obs = ServiceObservation(
            service_id="prod-db",
            cpu_utilization_percent=0.5,
            memory_utilization_percent=2.0,
            traffic_rpm=0,
            latency_ms=1.0,
            cost_per_hour=25.0,
            observation_timestamp=datetime.now(timezone.utc),
            state_version="db-v1",
        )
        proposal = ActionProposal(
            action=InfrastructureAction.STOP_IDLE_SERVICE,
            target_service_id="prod-db",
            reason="Stop production database during night",
            expected_effect="Cut DB cost",
            observation_version="db-v1",
            confidence=0.98,
        )

        result = engine.evaluate(proposal, obs)

        assert not result.is_approved
        assert "R07_PROTECTED_SERVICE" in result.applied_rules
        assert any("designated as protected/critical" in r for r in result.rejection_reasons)

    # 8. SCALE_DOWN SLA & Capacity Guard
    def test_scale_down_rejected_when_latency_breaches_sla(
        self, engine: DeterministicSafetyEngine
    ):
        """Scale down must be rejected if latency is above SLA ceiling (200ms)."""
        obs = ServiceObservation(
            service_id="web-frontend",
            cpu_utilization_percent=25.0,
            memory_utilization_percent=30.0,
            traffic_rpm=400,
            latency_ms=280.0,  # > 200ms
            cost_per_hour=3.0,
            observation_timestamp=datetime.now(timezone.utc),
            state_version="state-v100",
        )
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="web-frontend",
            reason="Cut frontend nodes",
            expected_effect="Save cost",
            observation_version="state-v100",
            confidence=0.89,
        )

        result = engine.evaluate(proposal, obs)

        assert not result.is_approved
        assert "R09_SCALE_DOWN_SLA_RISK" in result.applied_rules
        assert any("SLA breach risk" in r for r in result.rejection_reasons)

    def test_scale_down_rejected_when_cpu_high(
        self, engine: DeterministicSafetyEngine
    ):
        """Scale down must be rejected if CPU utilization > 40.0%."""
        obs = ServiceObservation(
            service_id="web-frontend",
            cpu_utilization_percent=68.0,  # > 40.0%
            memory_utilization_percent=30.0,
            traffic_rpm=400,
            latency_ms=80.0,
            cost_per_hour=3.0,
            observation_timestamp=datetime.now(timezone.utc),
            state_version="state-v100",
        )
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="web-frontend",
            reason="Scale down frontend nodes",
            expected_effect="Save cost",
            observation_version="state-v100",
            confidence=0.90,
        )

        result = engine.evaluate(proposal, obs)

        assert not result.is_approved
        assert any("capacity risk" in r for r in result.rejection_reasons)

    # 9. ExtendedServiceState & Capacity Validation (No raw schema mutation)
    def test_extended_service_capacity_limits(
        self, engine: DeterministicSafetyEngine, baseline_observation: ServiceObservation
    ):
        """Optional ExtendedServiceState enforces instance min/max floor without mutating ServiceObservation."""
        extended_state = ExtendedServiceState(
            observation=baseline_observation,
            capacity=ServiceCapacity(
                current_instances=1,
                min_instances=1,
                max_instances=10,
            ),
        )
        scale_down_proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="report-worker",
            reason="Scale down cluster",
            expected_effect="Cut instances",
            observation_version="state-v100",
            confidence=0.95,
        )

        result = engine.evaluate(scale_down_proposal, extended_state)

        assert not result.is_approved
        assert "R11_CAPACITY_FLOOR" in result.applied_rules
        assert any("at or below the minimum limit" in r for r in result.rejection_reasons)

    def test_extended_service_health_status_blocks_action(
        self, engine: DeterministicSafetyEngine, baseline_observation: ServiceObservation
    ):
        """Degraded or unhealthy service status blocks disruptive actions."""
        degraded_state = ExtendedServiceState(
            observation=baseline_observation,
            health_status=ServiceHealthStatus.DEGRADED,
        )
        scale_down_proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="report-worker",
            reason="Scale down during incident",
            expected_effect="Save cost",
            observation_version="state-v100",
            confidence=0.90,
        )

        result = engine.evaluate(scale_down_proposal, degraded_state)

        assert not result.is_approved
        assert "R06_UNHEALTHY_SERVICE" in result.applied_rules
        assert any("non-healthy status 'degraded'" in r for r in result.rejection_reasons)

    # 10. Workload Suitability Guard (DELAY_BATCH on Web Services)
    def test_delay_batch_rejected_on_web_service(
        self, engine: DeterministicSafetyEngine, baseline_observation: ServiceObservation
    ):
        """DELAY_BATCH cannot be applied to real-time web or API services."""
        web_state = ExtendedServiceState(
            observation=baseline_observation,
            service_type="web_service",
        )
        delay_proposal = ActionProposal(
            action=InfrastructureAction.DELAY_BATCH,
            target_service_id="report-worker",
            reason="Delay requests until morning",
            expected_effect="Flatten peak",
            observation_version="state-v100",
            confidence=0.88,
        )

        result = engine.evaluate(delay_proposal, web_state)

        assert not result.is_approved
        assert "R12_WORKLOAD_SUITABILITY" in result.applied_rules
        assert any("Cannot apply 'delay_batch' to real-time service" in r for r in result.rejection_reasons)

    # 11. Cooldown Anti-Flapping
    def test_action_cooldown_rate_limiting(
        self, engine: DeterministicSafetyEngine, baseline_observation: ServiceObservation, valid_idle_proposal: ActionProposal
    ):
        """Service in cooldown window cannot be acted upon."""
        now = datetime.now(timezone.utc)
        engine.record_action_execution("report-worker", timestamp=now - timedelta(seconds=45))

        context = SafetyContext(now=now)
        result = engine.evaluate(valid_idle_proposal, baseline_observation, context=context)

        assert not result.is_approved
        assert "R13_ACTION_COOLDOWN" in result.applied_rules
        assert any("is in cooldown" in r for r in result.rejection_reasons)

        # After cooldown duration expires
        context_after = SafetyContext(now=now + timedelta(seconds=350))
        result_after = engine.evaluate(valid_idle_proposal, baseline_observation, context=context_after)
        assert result_after.is_approved


class TestServiceStateModel:
    """Unit tests for the ServiceState model structure and constraints."""

    def test_service_state_creation_and_attributes(self):
        state = ServiceState(
            service_id="payment-service",
            current_instances=3,
            min_instances=1,
            max_instances=10,
            latency_ms=45.0,
            max_latency_ms=150.0,
            traffic_rpm=500,
            healthy=True,
            state_version="v1.0.0",
        )
        assert state.service_id == "payment-service"
        assert state.current_instances == 3
        assert state.min_instances == 1
        assert state.max_instances == 10
        assert state.latency_ms == 45.0
        assert state.max_latency_ms == 150.0
        assert state.traffic_rpm == 500
        assert state.healthy is True
        assert state.state_version == "v1.0.0"

    def test_service_state_bounds_validation(self):
        """min_instances cannot exceed max_instances."""
        with pytest.raises(ValueError, match="cannot exceed max_instances"):
            ServiceState(
                service_id="payment-service",
                current_instances=3,
                min_instances=10,
                max_instances=5,
                latency_ms=45.0,
                max_latency_ms=150.0,
                traffic_rpm=500,
                healthy=True,
                state_version="v1.0.0",
            )

    def test_service_state_from_observation(self, baseline_observation: ServiceObservation):
        """Factory method correctly maps observation into ServiceState."""
        state = ServiceState.from_observation(
            baseline_observation,
            current_instances=4,
            min_instances=2,
            max_instances=8,
            max_latency_ms=120.0,
            healthy=True,
        )
        assert state.service_id == baseline_observation.service_id
        assert state.current_instances == 4
        assert state.min_instances == 2
        assert state.max_instances == 8
        assert state.latency_ms == baseline_observation.latency_ms
        assert state.max_latency_ms == 120.0
        assert state.traffic_rpm == baseline_observation.traffic_rpm
        assert state.healthy is True
        assert state.state_version == baseline_observation.state_version


class TestInfrastructureSafetyGuardrails:
    """Unit tests for the 10 explicit infrastructure safety guardrail rules."""

    @pytest.fixture
    def default_service_state(self) -> ServiceState:
        return ServiceState(
            service_id="checkout-api",
            current_instances=4,
            min_instances=2,
            max_instances=8,
            latency_ms=50.0,
            max_latency_ms=200.0,
            traffic_rpm=400,
            healthy=True,
            state_version="state-v200",
        )

    # Rule 1: SCALE_DOWN must never reduce instances below min_instances
    def test_scale_down_below_min_instances_rejected(
        self, engine: DeterministicSafetyEngine, default_service_state: ServiceState
    ):
        """SCALE_DOWN proposal specifying target < min_instances must be rejected."""
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="checkout-api",
            reason="Scale down cluster to save cost",
            expected_effect="Reduce instances",
            observation_version="state-v200",
            confidence=0.95,
            target_instances=1,  # min_instances is 2
        )
        result = engine.evaluate(proposal, default_service_state)
        assert not result.is_approved
        assert "R11_CAPACITY_FLOOR" in result.applied_rules
        assert any("below the minimum limit" in r for r in result.rejection_reasons)

    def test_scale_down_when_already_at_min_instances_rejected(
        self, engine: DeterministicSafetyEngine
    ):
        """SCALE_DOWN when current_instances == min_instances must be rejected."""
        state = ServiceState(
            service_id="checkout-api",
            current_instances=2,
            min_instances=2,
            max_instances=8,
            latency_ms=50.0,
            max_latency_ms=200.0,
            traffic_rpm=400,
            healthy=True,
            state_version="state-v200",
        )
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="checkout-api",
            reason="Scale down cluster",
            expected_effect="Cut 1 instance",
            observation_version="state-v200",
            confidence=0.90,
        )
        result = engine.evaluate(proposal, state)
        assert not result.is_approved
        assert "R11_CAPACITY_FLOOR" in result.applied_rules
        assert any("already at or below the minimum limit" in r for r in result.rejection_reasons)

    def test_valid_scale_down_within_min_instances_approved(
        self, engine: DeterministicSafetyEngine, default_service_state: ServiceState
    ):
        """SCALE_DOWN to a target >= min_instances is approved."""
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="checkout-api",
            reason="Reduce 1 instance",
            expected_effect="Reduce from 4 to 3 instances",
            observation_version="state-v200",
            confidence=0.92,
            target_instances=3,  # min_instances is 2
        )
        result = engine.evaluate(proposal, default_service_state)
        assert result.is_approved
        assert "R11_CAPACITY_FLOOR" in result.applied_rules
        assert len(result.rejection_reasons) == 0

    # Rule 2: SCALE_UP must never increase instances above max_instances
    def test_scale_up_above_max_instances_rejected(
        self, engine: DeterministicSafetyEngine, default_service_state: ServiceState
    ):
        """SCALE_UP proposal specifying target > max_instances must be rejected."""
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_UP,
            target_service_id="checkout-api",
            reason="Handle peak load",
            expected_effect="Add instances",
            observation_version="state-v200",
            confidence=0.95,
            target_instances=12,  # max_instances is 8
        )
        result = engine.evaluate(proposal, default_service_state)
        assert not result.is_approved
        assert "R11_CAPACITY_CEILING" in result.applied_rules
        assert any("above maximum limit" in r for r in result.rejection_reasons)

    def test_scale_up_when_already_at_max_instances_rejected(
        self, engine: DeterministicSafetyEngine
    ):
        """SCALE_UP when current_instances == max_instances must be rejected."""
        state = ServiceState(
            service_id="checkout-api",
            current_instances=8,
            min_instances=2,
            max_instances=8,
            latency_ms=50.0,
            max_latency_ms=200.0,
            traffic_rpm=400,
            healthy=True,
            state_version="state-v200",
        )
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_UP,
            target_service_id="checkout-api",
            reason="Scale up cluster",
            expected_effect="Add 1 instance",
            observation_version="state-v200",
            confidence=0.90,
        )
        result = engine.evaluate(proposal, state)
        assert not result.is_approved
        assert "R11_CAPACITY_CEILING" in result.applied_rules
        assert any("already at or above maximum limit" in r for r in result.rejection_reasons)

    def test_valid_scale_up_within_max_instances_approved(
        self, engine: DeterministicSafetyEngine, default_service_state: ServiceState
    ):
        """SCALE_UP to target <= max_instances is approved."""
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_UP,
            target_service_id="checkout-api",
            reason="Scale up cluster",
            expected_effect="Increase from 4 to 6 instances",
            observation_version="state-v200",
            confidence=0.92,
            target_instances=6,  # max_instances is 8
        )
        result = engine.evaluate(proposal, default_service_state)
        assert result.is_approved
        assert "R11_CAPACITY_CEILING" in result.applied_rules
        assert len(result.rejection_reasons) == 0

    # Rule 3: Reject actions when service is unhealthy, unless emergency policy applies
    def test_unhealthy_service_rejects_scale_down(
        self, engine: DeterministicSafetyEngine
    ):
        """Unhealthy service rejects SCALE_DOWN by default."""
        unhealthy_state = ServiceState(
            service_id="checkout-api",
            current_instances=4,
            min_instances=2,
            max_instances=8,
            latency_ms=50.0,
            max_latency_ms=200.0,
            traffic_rpm=400,
            healthy=False,
            state_version="state-v200",
        )
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="checkout-api",
            reason="Scale down",
            expected_effect="Save money",
            observation_version="state-v200",
            confidence=0.90,
            target_instances=3,
        )
        result = engine.evaluate(proposal, unhealthy_state)
        assert not result.is_approved
        assert "R06_UNHEALTHY_SERVICE" in result.applied_rules
        assert any("non-healthy status" in r for r in result.rejection_reasons)

    def test_unhealthy_service_rejects_scale_up_without_emergency_policy(
        self, engine: DeterministicSafetyEngine
    ):
        """Unhealthy service rejects SCALE_UP when no emergency policy is set."""
        unhealthy_state = ServiceState(
            service_id="checkout-api",
            current_instances=4,
            min_instances=2,
            max_instances=8,
            latency_ms=50.0,
            max_latency_ms=200.0,
            traffic_rpm=400,
            healthy=False,
            state_version="state-v200",
        )
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_UP,
            target_service_id="checkout-api",
            reason="Emergency scale up",
            expected_effect="Relieve load",
            observation_version="state-v200",
            confidence=0.90,
            target_instances=6,
        )
        result = engine.evaluate(proposal, unhealthy_state)
        assert not result.is_approved
        assert "R06_UNHEALTHY_SERVICE" in result.applied_rules
        assert any("blocked during active degradation/outage" in r for r in result.rejection_reasons)

    def test_unhealthy_service_allows_scale_up_under_emergency_policy(
        self, engine: DeterministicSafetyEngine
    ):
        """EmergencyPolicy.ALLOW_SCALE_UP authorizes SCALE_UP on an unhealthy service."""
        unhealthy_state = ServiceState(
            service_id="checkout-api",
            current_instances=4,
            min_instances=2,
            max_instances=8,
            latency_ms=50.0,
            max_latency_ms=200.0,
            traffic_rpm=400,
            healthy=False,
            state_version="state-v200",
        )
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_UP,
            target_service_id="checkout-api",
            reason="Relieve OOM exhaustion",
            expected_effect="Restore health",
            observation_version="state-v200",
            confidence=0.95,
            target_instances=6,
        )
        context = SafetyContext(emergency_policy=EmergencyPolicy.ALLOW_SCALE_UP)
        result = engine.evaluate(proposal, unhealthy_state, context=context)

        assert result.is_approved
        assert "R06_UNHEALTHY_SERVICE" in result.applied_rules
        assert "R16_EMERGENCY_POLICY" in result.applied_rules
        assert len(result.rejection_reasons) == 0

    def test_unhealthy_service_blocks_scale_down_even_under_emergency_policy(
        self, engine: DeterministicSafetyEngine
    ):
        """EmergencyPolicy.ALLOW_SCALE_UP strictly blocks SCALE_DOWN on an unhealthy service."""
        unhealthy_state = ServiceState(
            service_id="checkout-api",
            current_instances=4,
            min_instances=2,
            max_instances=8,
            latency_ms=50.0,
            max_latency_ms=200.0,
            traffic_rpm=400,
            healthy=False,
            state_version="state-v200",
        )
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="checkout-api",
            reason="Scale down cluster",
            expected_effect="Cut nodes",
            observation_version="state-v200",
            confidence=0.90,
            target_instances=3,
        )
        context = SafetyContext(emergency_policy=EmergencyPolicy.ALLOW_SCALE_UP)
        result = engine.evaluate(proposal, unhealthy_state, context=context)

        assert not result.is_approved
        assert "R06_UNHEALTHY_SERVICE" in result.applied_rules
        assert "R16_EMERGENCY_POLICY" in result.applied_rules
        assert any("Emergency policy 'allow_scale_up' permits only emergency SCALE_UP" in r for r in result.rejection_reasons)

    # Rule 4: Reject proposals based on stale state versions
    def test_stale_state_version_rejected_on_service_state(
        self, engine: DeterministicSafetyEngine, default_service_state: ServiceState
    ):
        """Proposal based on outdated state version is rejected."""
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_UP,
            target_service_id="checkout-api",
            reason="Scale up",
            expected_effect="Add 1 node",
            observation_version="state-v199",  # state is state-v200
            confidence=0.90,
        )
        result = engine.evaluate(proposal, default_service_state)
        assert not result.is_approved
        assert "R01_STALE_STATE" in result.applied_rules
        assert result.proposal_version == "state-v199"
        assert result.evaluated_against_version == "state-v200"

    # Rule 5: Reject unknown service IDs
    def test_unknown_service_id_in_catalog_rejected(
        self, engine: DeterministicSafetyEngine
    ):
        """Service ID not present in registered known services catalog must be rejected."""
        engine.register_services(["checkout-api", "payment-service", "user-service"])

        state = ServiceState(
            service_id="ghost-service",
            current_instances=3,
            min_instances=1,
            max_instances=5,
            latency_ms=30.0,
            max_latency_ms=100.0,
            traffic_rpm=100,
            healthy=True,
            state_version="v1",
        )
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_UP,
            target_service_id="ghost-service",
            reason="Scale up unknown service",
            expected_effect="More instances",
            observation_version="v1",
            confidence=0.90,
        )
        result = engine.evaluate(proposal, state)
        assert not result.is_approved
        assert "R14_UNKNOWN_SERVICE" in result.applied_rules
        assert any("not present in the known service catalog" in r for r in result.rejection_reasons)

    def test_empty_or_whitespace_target_service_rejected(
        self, engine: DeterministicSafetyEngine, default_service_state: ServiceState
    ):
        """Empty or blank target service ID must be rejected."""
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_UP,
            target_service_id="   ",
            reason="Scale up",
            expected_effect="More instances",
            observation_version="state-v200",
            confidence=0.90,
        )
        result = engine.evaluate(proposal, default_service_state)
        assert not result.is_approved
        assert "R14_UNKNOWN_SERVICE" in result.applied_rules
        assert any("invalid or unassigned" in r for r in result.rejection_reasons)

    # Rule 6: Reject invalid target instance counts
    def test_negative_target_instances_rejected(
        self, engine: DeterministicSafetyEngine, default_service_state: ServiceState
    ):
        """Negative target instance count must be rejected."""
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="checkout-api",
            reason="Scale down",
            expected_effect="Cut instances",
            observation_version="state-v200",
            confidence=0.90,
            target_instances=-2,
        )
        result = engine.evaluate(proposal, default_service_state)
        assert not result.is_approved
        assert "R15_INVALID_TARGET_INSTANCES" in result.applied_rules
        assert any("cannot be negative" in r for r in result.rejection_reasons)

    def test_scale_down_with_target_greater_than_or_equal_to_current_rejected(
        self, engine: DeterministicSafetyEngine, default_service_state: ServiceState
    ):
        """SCALE_DOWN with target >= current_instances is contradictory and must be rejected."""
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="checkout-api",
            reason="Scale down",
            expected_effect="Cut instances",
            observation_version="state-v200",
            confidence=0.90,
            target_instances=5,  # current is 4!
        )
        result = engine.evaluate(proposal, default_service_state)
        assert not result.is_approved
        assert "R15_INVALID_TARGET_INSTANCES" in result.applied_rules
        assert any("target must be strictly less than current instances" in r for r in result.rejection_reasons)

    def test_scale_up_with_target_less_than_or_equal_to_current_rejected(
        self, engine: DeterministicSafetyEngine, default_service_state: ServiceState
    ):
        """SCALE_UP with target <= current_instances is contradictory and must be rejected."""
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_UP,
            target_service_id="checkout-api",
            reason="Scale up",
            expected_effect="Add instances",
            observation_version="state-v200",
            confidence=0.90,
            target_instances=3,  # current is 4!
        )
        result = engine.evaluate(proposal, default_service_state)
        assert not result.is_approved
        assert "R15_INVALID_TARGET_INSTANCES" in result.applied_rules
        assert any("target must be strictly greater than current instances" in r for r in result.rejection_reasons)

    # Rule 7: Ensure latency constraints are evaluated deterministically
    def test_scale_down_rejected_when_current_latency_exceeds_max_latency_ms(
        self, engine: DeterministicSafetyEngine
    ):
        """SCALE_DOWN rejected deterministically when current latency exceeds max_latency_ms."""
        state = ServiceState(
            service_id="checkout-api",
            current_instances=5,
            min_instances=2,
            max_instances=10,
            latency_ms=180.0,
            max_latency_ms=150.0,  # current (180ms) > max (150ms)
            traffic_rpm=300,
            healthy=True,
            state_version="v1",
        )
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="checkout-api",
            reason="Scale down",
            expected_effect="Save cost",
            observation_version="v1",
            confidence=0.90,
            target_instances=4,
        )
        result = engine.evaluate(proposal, state)
        assert not result.is_approved
        assert "R09_SCALE_DOWN_SLA_RISK" in result.applied_rules
        assert any("exceeds safe ceiling (150.0ms)" in r for r in result.rejection_reasons)

    def test_scale_down_rejected_when_projected_latency_exceeds_max_latency_ms(
        self, engine: DeterministicSafetyEngine
    ):
        """SCALE_DOWN rejected deterministically when projected latency exceeds max_latency_ms.

        Current latency = 120ms with 4 instances.
        Max latency = 150ms.
        If scaling down to 2 instances:
        projected = 120 * (4 / 2) = 240ms > 150ms!
        """
        state = ServiceState(
            service_id="checkout-api",
            current_instances=4,
            min_instances=1,
            max_instances=10,
            latency_ms=120.0,
            max_latency_ms=150.0,
            traffic_rpm=500,
            healthy=True,
            state_version="v1",
        )
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="checkout-api",
            reason="Scale down aggressively",
            expected_effect="Cut 2 instances",
            observation_version="v1",
            confidence=0.90,
            target_instances=2,
        )
        result = engine.evaluate(proposal, state)
        assert not result.is_approved
        assert "R09_SCALE_DOWN_SLA_RISK" in result.applied_rules
        assert any("projected latency (240.0ms)" in r for r in result.rejection_reasons)

    # Rule 8, 9, 10: Schema compatibility, rule reporting, and pure validation
    def test_applied_rules_and_rejection_reasons_present(
        self, engine: DeterministicSafetyEngine, default_service_state: ServiceState
    ):
        """Result must contain applied_rules list and rejection_reasons list."""
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="checkout-api",
            reason="Scale down",
            expected_effect="Save cost",
            observation_version="state-v200",
            confidence=0.95,
            target_instances=3,
        )
        result = engine.evaluate(proposal, default_service_state)
        assert isinstance(result, SafetyCheckResult)
        assert isinstance(result.applied_rules, list)
        assert isinstance(result.rejection_reasons, list)
        assert result.is_approved is True
        assert len(result.applied_rules) > 0
        assert len(result.rejection_reasons) == 0


class TestModularRuleFunctions:
    """Unit tests verifying modular, testable rule functions independently."""

    def test_validate_state_freshness(self):
        code, err = validate_state_freshness("v1", "v1")
        assert code == "R01_STALE_STATE"
        assert err is None

        code, err = validate_state_freshness("v1", "v2")
        assert code == "R01_STALE_STATE"
        assert "Stale observation" in err

    def test_validate_service_identity(self):
        codes, reasons = validate_service_identity("auth-svc", "auth-svc", {"auth-svc", "web-svc"})
        assert len(reasons) == 0

        codes, reasons = validate_service_identity("unknown-svc", "unknown-svc", {"auth-svc", "web-svc"})
        assert any("not present in the known service catalog" in r for r in reasons)

        codes, reasons = validate_service_identity("auth-svc", "other-svc")
        assert any("Target service mismatch" in r for r in reasons)

    def test_validate_target_instance_counts(self):
        codes, reasons = validate_target_instance_counts(InfrastructureAction.SCALE_DOWN, 5, 6)
        assert any("must be strictly less" in r for r in reasons)

        codes, reasons = validate_target_instance_counts(InfrastructureAction.SCALE_UP, 5, 4)
        assert any("must be strictly greater" in r for r in reasons)

        codes, reasons = validate_target_instance_counts(InfrastructureAction.SCALE_UP, 5, -1)
        assert any("cannot be negative" in r for r in reasons)

    def test_validate_capacity_bounds(self):
        codes, reasons = validate_capacity_bounds(InfrastructureAction.SCALE_DOWN, 2, 2, 10, None)
        assert any("already at or below" in r for r in reasons)

        codes, reasons = validate_capacity_bounds(InfrastructureAction.SCALE_UP, 10, 1, 10, None)
        assert any("already at or above" in r for r in reasons)

    def test_validate_service_health(self):
        codes, reasons = validate_service_health(
            InfrastructureAction.SCALE_DOWN, False, "unhealthy", EmergencyPolicy.NONE
        )
        assert any("blocked during active degradation" in r for r in reasons)

        # Scale up with emergency policy
        codes, reasons = validate_service_health(
            InfrastructureAction.SCALE_UP, False, "unhealthy", EmergencyPolicy.ALLOW_SCALE_UP
        )
        assert len(reasons) == 0

    def test_validate_latency_constraints(self):
        # Latency above ceiling
        codes, reasons = validate_latency_constraints(
            InfrastructureAction.SCALE_DOWN, 250.0, 200.0, 5, 4, 200.0
        )
        assert any("exceeds safe ceiling" in r for r in reasons)

        # Projected latency above ceiling: current 150ms on 4 instances -> 2 instances = 300ms > 200ms
        codes, reasons = validate_latency_constraints(
            InfrastructureAction.SCALE_DOWN, 150.0, 200.0, 4, 2, 200.0
        )
        assert any("projected latency" in r for r in reasons)


class TestExplicitRequiredSafetyCases:
    """Explicit test suite covering all exact scenarios requested for Person 2."""

    @pytest.fixture
    def four_instance_state(self) -> ServiceState:
        """4 instances, minimum = 2, maximum = 8."""
        return ServiceState(
            service_id="app-service",
            current_instances=4,
            min_instances=2,
            max_instances=8,
            latency_ms=50.0,
            max_latency_ms=200.0,
            traffic_rpm=300,
            healthy=True,
            state_version="v2",
        )

    @pytest.fixture
    def six_instance_state(self) -> ServiceState:
        """6 instances, minimum = 2, maximum = 8."""
        return ServiceState(
            service_id="app-service",
            current_instances=6,
            min_instances=2,
            max_instances=8,
            latency_ms=50.0,
            max_latency_ms=200.0,
            traffic_rpm=450,
            healthy=True,
            state_version="v2",
        )

    # 1. Valid scale-down: 4 instances -> 2 instances, minimum = 2 -> approve
    def test_valid_scale_down_four_to_two_instances(
        self, engine: DeterministicSafetyEngine, four_instance_state: ServiceState
    ):
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="app-service",
            reason="Scale down to target capacity",
            expected_effect="Cost reduction",
            observation_version="v2",
            confidence=0.95,
            target_instances=2,
        )
        result = engine.evaluate(proposal, four_instance_state)
        assert result.is_approved is True
        assert "R11_CAPACITY_FLOOR" in result.applied_rules
        assert len(result.rejection_reasons) == 0

    # 2. Scale-down below minimum: 4 instances -> 1 instance, minimum = 2 -> reject
    def test_scale_down_below_minimum_four_to_one_instance(
        self, engine: DeterministicSafetyEngine, four_instance_state: ServiceState
    ):
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="app-service",
            reason="Scale down aggressively",
            expected_effect="Cut costs further",
            observation_version="v2",
            confidence=0.95,
            target_instances=1,
        )
        result = engine.evaluate(proposal, four_instance_state)
        assert result.is_approved is False
        assert "R11_CAPACITY_FLOOR" in result.applied_rules
        assert any("below the minimum limit" in r for r in result.rejection_reasons)

    # 3. Scale-up above maximum: 6 instances -> 9 instances, maximum = 8 -> reject
    def test_scale_up_above_maximum_six_to_nine_instances(
        self, engine: DeterministicSafetyEngine, six_instance_state: ServiceState
    ):
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_UP,
            target_service_id="app-service",
            reason="Handle spike",
            expected_effect="Increase capacity",
            observation_version="v2",
            confidence=0.95,
            target_instances=9,
        )
        result = engine.evaluate(proposal, six_instance_state)
        assert result.is_approved is False
        assert "R11_CAPACITY_CEILING" in result.applied_rules
        assert any("above maximum limit" in r for r in result.rejection_reasons)

    # 4. Stale state version: Proposal version v1, current state version v2 -> reject
    def test_stale_state_version_v1_against_v2(
        self, engine: DeterministicSafetyEngine, four_instance_state: ServiceState
    ):
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="app-service",
            reason="Scale down cluster",
            expected_effect="Reduce instances",
            observation_version="v1",
            confidence=0.95,
            target_instances=2,
        )
        result = engine.evaluate(proposal, four_instance_state)
        assert result.is_approved is False
        assert "R01_STALE_STATE" in result.applied_rules
        assert result.proposal_version == "v1"
        assert result.evaluated_against_version == "v2"
        assert any("Stale observation detected" in r for r in result.rejection_reasons)

    # 5. Unhealthy service: Verify unsafe actions on an unhealthy service are rejected
    def test_unhealthy_service_rejects_unsafe_actions(
        self, engine: DeterministicSafetyEngine
    ):
        unhealthy_state = ServiceState(
            service_id="app-service",
            current_instances=4,
            min_instances=2,
            max_instances=8,
            latency_ms=50.0,
            max_latency_ms=200.0,
            traffic_rpm=300,
            healthy=False,
            state_version="v2",
        )
        for unsafe_action in [
            InfrastructureAction.SCALE_DOWN,
            InfrastructureAction.SCALE_UP,
            InfrastructureAction.STOP_IDLE_SERVICE,
            InfrastructureAction.RESIZE,
            InfrastructureAction.DELAY_BATCH,
        ]:
            proposal = ActionProposal(
                action=unsafe_action,
                target_service_id="app-service",
                reason="Attempt action on unhealthy service",
                expected_effect="Unknown",
                observation_version="v2",
                confidence=0.95,
            )
            result = engine.evaluate(proposal, unhealthy_state)
            assert result.is_approved is False
            assert "R06_UNHEALTHY_SERVICE" in result.applied_rules
            assert any("non-healthy status" in r for r in result.rejection_reasons)

    # 6. Unknown service: Target a service that does not exist -> reject
    def test_unknown_service_target_rejected(
        self, engine: DeterministicSafetyEngine, four_instance_state: ServiceState
    ):
        engine.register_services(["app-service", "billing-service"])
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="non-existent-service",
            reason="Scale down missing service",
            expected_effect="Cut nodes",
            observation_version="v2",
            confidence=0.90,
            target_instances=2,
        )
        result = engine.evaluate(proposal, four_instance_state)
        assert result.is_approved is False
        assert "R14_UNKNOWN_SERVICE" in result.applied_rules
        assert any("not present in the known service catalog" in r for r in result.rejection_reasons)

    # 7. Invalid target: Verify invalid target information is handled safely
    @pytest.mark.parametrize("invalid_target", [-1, -10, 0])
    def test_invalid_target_instances_handled_safely(
        self, engine: DeterministicSafetyEngine, four_instance_state: ServiceState, invalid_target: int
    ):
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="app-service",
            reason="Invalid target count",
            expected_effect="Invalid",
            observation_version="v2",
            confidence=0.95,
            target_instances=invalid_target,
        )
        result = engine.evaluate(proposal, four_instance_state)
        assert result.is_approved is False
        assert (
            "R15_INVALID_TARGET_INSTANCES" in result.applied_rules
            or "R11_CAPACITY_FLOOR" in result.applied_rules
        )

    def test_invalid_target_service_id_empty_or_whitespace(
        self, engine: DeterministicSafetyEngine, four_instance_state: ServiceState
    ):
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="   ",
            reason="Blank service id",
            expected_effect="None",
            observation_version="v2",
            confidence=0.95,
            target_instances=2,
        )
        result = engine.evaluate(proposal, four_instance_state)
        assert result.is_approved is False
        assert "R14_UNKNOWN_SERVICE" in result.applied_rules
        assert any("invalid or unassigned" in r for r in result.rejection_reasons)

    # 8. NO_ACTION: Test the expected behavior for NO_ACTION
    def test_no_action_approved_when_fresh_rejected_when_stale(
        self, engine: DeterministicSafetyEngine, four_instance_state: ServiceState
    ):
        fresh_no_action = ActionProposal(
            action=InfrastructureAction.NO_ACTION,
            target_service_id="app-service",
            reason="System operating within parameters",
            expected_effect="Maintain stability",
            observation_version="v2",
            confidence=0.50,
        )
        result_fresh = engine.evaluate(fresh_no_action, four_instance_state)
        assert result_fresh.is_approved is True
        assert "R04_NO_ACTION_SAFE" in result_fresh.applied_rules
        assert len(result_fresh.rejection_reasons) == 0

        stale_no_action = ActionProposal(
            action=InfrastructureAction.NO_ACTION,
            target_service_id="app-service",
            reason="Nominal",
            expected_effect="Maintain",
            observation_version="v1",  # stale
            confidence=0.90,
        )
        result_stale = engine.evaluate(stale_no_action, four_instance_state)
        assert result_stale.is_approved is False
        assert "R01_STALE_STATE" in result_stale.applied_rules

    # 9. Latency guardrail: Test latency protection rules
    def test_latency_guardrail_current_and_projected_breach(
        self, engine: DeterministicSafetyEngine
    ):
        # Current latency exceeds SLA ceiling
        high_latency_state = ServiceState(
            service_id="app-service",
            current_instances=4,
            min_instances=1,
            max_instances=8,
            latency_ms=250.0,
            max_latency_ms=200.0,
            traffic_rpm=300,
            healthy=True,
            state_version="v2",
        )
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="app-service",
            reason="Scale down cluster",
            expected_effect="Save cost",
            observation_version="v2",
            confidence=0.90,
            target_instances=3,
        )
        result = engine.evaluate(proposal, high_latency_state)
        assert result.is_approved is False
        assert "R09_SCALE_DOWN_SLA_RISK" in result.applied_rules
        assert any("exceeds safe ceiling" in r for r in result.rejection_reasons)

        # Projected latency exceeds SLA ceiling (150ms * 4 / 2 = 300ms > 200ms)
        safe_current_state = ServiceState(
            service_id="app-service",
            current_instances=4,
            min_instances=1,
            max_instances=8,
            latency_ms=150.0,
            max_latency_ms=200.0,
            traffic_rpm=300,
            healthy=True,
            state_version="v2",
        )
        proposal_aggressive = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="app-service",
            reason="Aggressive scale down",
            expected_effect="Cut in half",
            observation_version="v2",
            confidence=0.90,
            target_instances=2,
        )
        result_proj = engine.evaluate(proposal_aggressive, safe_current_state)
        assert result_proj.is_approved is False
        assert "R09_SCALE_DOWN_SLA_RISK" in result_proj.applied_rules
        assert any("projected latency" in r for r in result_proj.rejection_reasons)

    # 10. Test deterministic behavior with identical inputs
    def test_deterministic_behavior_with_identical_inputs(
        self, engine: DeterministicSafetyEngine, four_instance_state: ServiceState
    ):
        proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="app-service",
            reason="Scale down cluster",
            expected_effect="Save cost",
            observation_version="v2",
            confidence=0.92,
            target_instances=2,
        )
        first_result = engine.evaluate(proposal, four_instance_state)

        for _ in range(5):
            subsequent_result = engine.evaluate(proposal, four_instance_state)
            assert subsequent_result.is_approved == first_result.is_approved
            assert subsequent_result.applied_rules == first_result.applied_rules
            assert subsequent_result.rejection_reasons == first_result.rejection_reasons
            assert subsequent_result.proposal_version == first_result.proposal_version
            assert subsequent_result.evaluated_against_version == first_result.evaluated_against_version

    # 11. Ensure stale-version protection cannot be bypassed
    def test_stale_version_protection_cannot_be_bypassed(
        self, engine: DeterministicSafetyEngine, four_instance_state: ServiceState
    ):
        # Even with max confidence, cooldown bypass, and emergency policy:
        stale_proposal = ActionProposal(
            action=InfrastructureAction.SCALE_DOWN,
            target_service_id="app-service",
            reason="Scale down",
            expected_effect="Save cost",
            observation_version="v_stale",
            confidence=1.0,
            target_instances=2,
        )
        context = SafetyContext(
            bypass_cooldown=True,
            emergency_policy=EmergencyPolicy.ALLOW_SCALE_UP,
        )
        result = engine.evaluate(stale_proposal, four_instance_state, context=context)
        assert result.is_approved is False
        assert "R01_STALE_STATE" in result.applied_rules
        assert any("Stale observation detected" in r for r in result.rejection_reasons)


