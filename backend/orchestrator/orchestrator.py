from typing import Callable, Optional                                      
import uuid                                                            
from backend.services.execution_service import ExecutionService        
from backend.agents.verification_agent import VerificationAgent        
from backend.schemas.metrics import ServiceObservation
from backend.schemas.actions import ActionProposal, InfrastructureAction
from backend.schemas.workflow import DecisionResult, WorkflowReport
from backend.schemas.execution import ExecutionResult, ExecutionStatus
from backend.agents.investigation_agent import InvestigationAgent
from backend.agents.decision_agent import DecisionAgent
from backend.agents.safety_engine import SafetyEngine
from backend.agents.verification_agent import VerificationAgent

class Orchestrator:
    """
    Coordinates the agent workflow for analyzing cloud metrics and making scaling decisions.
    Uses injected dependencies for execution and re-observation to ensure separation of concerns.
    """

    def __init__(
        self,
        investigation_agent: InvestigationAgent = None,
        decision_agent: DecisionAgent = None,
        safety_engine: SafetyEngine = None,
        verification_agent: VerificationAgent = None,
        executor: Optional[Callable[[ActionProposal], ExecutionResult]] = None,
        observer: Optional[Callable[[str], ServiceObservation]] = None
    ):
        self.investigation_agent = investigation_agent or InvestigationAgent()
        self.decision_agent = decision_agent or DecisionAgent()
        self.safety_engine = safety_engine or SafetyEngine()
        self.verification_agent = verification_agent or VerificationAgent()
        self.execution_service = ExecutionService()
        self.executor = executor or self.execution_service.execute
        self.observer = observer

    def run(self, observation: ServiceObservation) -> WorkflowReport:
        """
        Executes the main observe -> investigate -> decide -> safety -> execute -> verify loop.
        """
        # 1. Investigate
        investigation = self.investigation_agent.investigate(observation)
        
        # 2. Decide
        decision = self.decision_agent.decide(investigation)
        proposal = decision.proposal
        
        # 3. Safety Check
        safety_check = self.safety_engine.check(proposal, observation)
        
        execution_result = None
        post_observation = None
        
        # 4. Execute (only if approved and not NO_ACTION)
        if safety_check.is_approved and proposal.action != InfrastructureAction.NO_ACTION:
            if self.executor:
                execution_result = self.executor(proposal)
                
                # 5. Observe Again (if execution successful and observer available)
                if execution_result.status == ExecutionStatus.SUCCESS and self.observer:
                    post_observation = self.observer(proposal.target_service_id)
        
        # 6. Verify
        verification = self.verification_agent.verify(
            decision=decision,
            safety_check=safety_check,
            execution=execution_result,
            post_execution_observation=post_observation
        )
        
        # 7. Report
        return WorkflowReport(
            workflow_id=str(uuid.uuid4()),
            initial_observation=observation,
            final_verification=verification
        )
