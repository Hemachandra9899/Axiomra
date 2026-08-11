"""Risk policy and engine.

An order CANNOT be sent if `RiskDecision.approved` is False. This is the
authority boundary in the pipeline; nothing else may approve an order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from axiomra.domain.portfolio import RiskCheck
from axiomra.risk.context import RiskContext
from axiomra.risk.rules import RiskRule, compile_rules
from axiomra.versions import RISK_POLICY_VERSION


class RiskDecision(BaseModel):
    approved: bool
    checks: list[RiskCheck] = Field(default_factory=list)
    policy_version: str = ""

    @property
    def reasons(self) -> list[str]:
        return [
            check.reason
            for check in self.checks
            if not check.passed and check.reason is not None
        ]


@dataclass
class RiskPolicy:
    """A versioned, named set of rules."""

    name: str
    version: str
    rules: list[RiskRule] = field(default_factory=list)

    @classmethod
    def defaults(
        cls,
        name: str = "axiomra-default",
        version: str = RISK_POLICY_VERSION,
    ) -> RiskPolicy:
        return cls(name=name, version=version, rules=compile_rules())


class RiskEngine:
    """Evaluates a RiskContext against a RiskPolicy."""

    def __init__(self, policy: RiskPolicy | None = None) -> None:
        self.policy = policy or RiskPolicy.defaults()

    def evaluate(self, ctx: RiskContext) -> RiskDecision:
        checks = [rule.check(ctx) for rule in self.policy.rules]
        approved = all(check.passed for check in checks)
        return RiskDecision(
            approved=approved,
            checks=checks,
            policy_version=f"{self.policy.name}@{self.policy.version}",
        )
