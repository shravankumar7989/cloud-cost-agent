export type InfrastructureAction = 
  | "scale_up"
  | "scale_down"
  | "resize"
  | "stop_idle_service"
  | "delay_batch_job"
  | "no_action";

export type ExecutionStatus = "SUCCESS" | "FAILURE";

export interface ServiceObservation {
  service_id: string;
  cpu_utilization_percent: number;
  memory_utilization_percent: number;
  traffic_rpm: number;
  latency_ms: number;
  cost_per_hour: number;
  observation_timestamp: string; // ISO datetime string
  state_version: string;
}

export interface ServiceState {
  current_instances: number;
  min_instances: number;
  max_instances: number;
  latency_ms: number;
  max_latency_ms: number;
  traffic_rpm: number;
  healthy: boolean;
  state_version: string;
  cpu_utilization_percent: number;
  memory_utilization_percent: number;
  cost_per_hour: number;
  service_type: string;
  is_critical: boolean;
}

export interface InvestigationResult {
  observation: ServiceObservation;
  identified_issues: string[];
  summary: string;
}

export interface ActionProposal {
  action: InfrastructureAction;
  target_service_id: string;
  reason: string;
  expected_effect: string;
  observation_version: string;
  confidence: number;
}

export interface DecisionResult {
  investigation: InvestigationResult;
  proposal: ActionProposal;
}

export interface SafetyCheckResult {
  is_approved: boolean;
  proposal_version: string;
  evaluated_against_version: string;
  rejection_reasons: string[];
  applied_rules: string[];
}

export interface ExecutionResult {
  action: InfrastructureAction;
  target_service_id: string;
  status: ExecutionStatus;
  error_code: string | null;
  error_message: string | null;
  new_state_version: string | null;
}

export interface VerificationResult {
  decision: DecisionResult;
  safety_check: SafetyCheckResult;
  execution: ExecutionResult | null;
  is_successful: boolean;
  verification_notes: string;
}

export interface WorkflowReport {
  workflow_id: string;
  initial_observation: ServiceObservation;
  final_verification: VerificationResult;
}

// Additional type to represent a full scenario timeline for UI playback
export interface Scenario {
  id: string;
  name: string;
  description: string;
  initialState: Record<string, ServiceState>; // Map of serviceId to state
  workflow: WorkflowReport;
}
