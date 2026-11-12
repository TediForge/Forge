# Manages transient execution state, intermediate step outputs, and shared variables across multi-modal orchestrator runs

from typing import Dict, Any, Optional


class ExecutionState:
    """
    Holds variables, step outputs, and metadata during an active execution run.
    """
    def __init__(self, runId: str, initialPayload: Optional[Dict[str, Any]] = None):
        self.runId = runId
        self._store: Dict[str, Any] = initialPayload or {}
        self._stepOutputs: Dict[int, Any] = {}

    def setVariable(self, key: str, value: Any):
        """Stores a custom transient variable."""
        self._store[key] = value

    def getVariable(self, key: str, default: Any = None) -> Any:
        """Retrieves a stored variable."""
        return self._store.get(key, default)

    def recordStepOutput(self, stepId: int, output: Any):
        """Saves the result of a completed execution step."""
        self._stepOutputs[stepId] = output

    def getStepOutput(self, stepId: int) -> Any:
        """Retrieves output from a previous step to feed into a dependent step."""
        return self._stepOutputs.get(stepId)

    def setScratchpad(self, key: str, value: Any) -> None:
        scratchpad = self._store.setdefault("scratchpad", {})
        scratchpad[key] = value

    def getScratchpad(self, key: str, default: Any = None) -> Any:
        return self._store.get("scratchpad", {}).get(key, default)

    def recordAgentMessage(self, message: Any) -> None:
        messages = self._store.setdefault("agentMessages", [])
        messages.append(message.to_dict() if hasattr(message, "to_dict") else message)

    def getAgentMessages(self, recipient: Optional[str] = None, kind: Optional[str] = None) -> list[Any]:
        messages = self._store.get("agentMessages", [])
        return [
            message for message in messages
            if (recipient is None or message.get("recipient") == recipient)
            and (kind is None or message.get("kind") == kind)
        ]

    def exportState(self) -> Dict[str, Any]:
        """Exports the full current state for logging or debugging."""
        safeVariables = {
            key: value
            for key, value in self._store.items()
            if key not in {"attachmentContents", "inlineAttachments", "sessionHistory", "refinedPrompt"}
        }
        return {
            "runId": self.runId,
            "variables": safeVariables,
            "stepOutputs": self._stepOutputs
        }

    @classmethod
    def fromExport(cls, payload: Dict[str, Any]) -> "ExecutionState":
        if not isinstance(payload, dict) or not isinstance(payload.get("runId"), str):
            raise ValueError("Invalid execution checkpoint")
        variables = payload.get("variables", {})
        step_outputs = payload.get("stepOutputs", {})
        if not isinstance(variables, dict) or not isinstance(step_outputs, dict):
            raise ValueError("Invalid execution checkpoint state")
        state = cls(runId=payload["runId"], initialPayload=variables)
        try:
            state._stepOutputs = {int(step_id): output for step_id, output in step_outputs.items()}
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid checkpoint step output") from exc
        return state