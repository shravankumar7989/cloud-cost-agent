from backend.schemas.metrics import ServiceObservation
from backend.schemas.workflow import DecisionResult
from backend.agents.investigation_agent import InvestigationAgent
from backend.agents.decision_agent import DecisionAgent

class Orchestrator:
    """
    Coordinates the agent workflow for analyzing cloud metrics and making scaling decisions.
    """

    def __init__(self, investigation_agent: InvestigationAgent = None, decision_agent: DecisionAgent = None):
        self.investigation_agent = investigation_agent or InvestigationAgent()
        self.decision_agent = decision_agent or DecisionAgent()

    def run(self, observation: ServiceObservation) -> DecisionResult:
        """
        Executes the main observe -> investigate -> decide loop.
        """
        investigation = self.investigation_agent.investigate(observation)
        decision = self.decision_agent.decide(investigation)
        return decision
