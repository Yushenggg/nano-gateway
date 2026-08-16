from abc import ABC, abstractmethod
from pydantic import BaseModel
from nanogateway.models import ChatMessage


class GuardrailResult(BaseModel):
    passed: bool
    reason: str | None = None


class BaseGuardrail(ABC):
    @abstractmethod
    def check(self, messages: list[ChatMessage]) -> GuardrailResult: ...


class GuardrailRegistry:
    def __init__(self):
        self._guardrails: list[BaseGuardrail] = []

    def register(self, guardrail: BaseGuardrail):
        self._guardrails.append(guardrail)

    def check_all(self, messages: list[ChatMessage]) -> GuardrailResult:
        for g in self._guardrails:
            result = g.check(messages)
            if not result.passed:
                return result
        return GuardrailResult(passed=True)
