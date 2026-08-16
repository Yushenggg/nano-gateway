import re
from nanogateway.guardrails import BaseGuardrail, GuardrailResult
from nanogateway.models import ChatMessage


PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"you\s+are\s+now\s+(?:DAN|jailbroken|in\s+developer\s+mode)",
    r"system\s*prompt",
    r"reveal\s+(?:your|the)\s+(?:instructions|prompt|rules)",
    r"repeat\s+(?:everything|all)\s+(?:above|before)",
    r"disregard\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|rules)",
    r"act\s+as\s+if\s+you\s+(?:have\s+no|are\s+free\s+from)\s+(?:restrictions|rules)",
    r"bypass\s+(?:all\s+)?(?:safety|content)\s+(?:filter|restriction)",
    r"forget\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|rules)",
    r"override\s+(?:your|all)\s+(?:instructions|rules|programming)",
    r"you\s+are\s+(?:an?\s+)?(?:unrestricted|unfiltered|uncensored)",
    r"pretend\s+you\s+(?:are|have)\s+no\s+(?:restrictions|rules|guidelines)",
    r"do\s+anything\s+now",
    r"jailbreak",
    r"\bDAN\b.*\bmode\b",
]


class InjectionGuardrail(BaseGuardrail):
    def check(self, messages: list[ChatMessage]) -> GuardrailResult:
        for msg in messages:
            if msg.content and isinstance(msg.content, str):
                for pattern in PATTERNS:
                    if re.search(pattern, msg.content, re.IGNORECASE):
                        return GuardrailResult(
                            passed=False,
                            reason=f"Blocked: matched pattern '{pattern}'",
                        )
        return GuardrailResult(passed=True)
