"""Explicit sales-conversation state machine. Invalid transitions raise; the LLM never drives this."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class State(StrEnum):
    ELIGIBILITY_CHECK = "eligibility_check"
    CALL_AUTHORIZATION = "call_authorization"
    DIAL_REQUEST = "dial_request"
    DIALING = "dialing"
    RINGING = "ringing"
    CONNECTED = "connected"
    GREETING = "greeting"  # greeting + identity disclosure
    PERMISSION_TO_CONTINUE = "permission_to_continue"
    NEEDS_DISCOVERY = "needs_discovery"
    PRODUCT_EXPLANATION = "product_explanation"
    OBJECTION_HANDLING = "objection_handling"
    DEMO_INVITATION = "demo_invitation"
    HUMAN_HANDOFF = "human_handoff"
    FOLLOWUP_SCHEDULING = "followup_scheduling"
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    TECHNICAL_FAILURE = "technical_failure"
    CANCELLED = "cancelled"
    OPTED_OUT = "opted_out"


TERMINAL = {State.COMPLETED, State.NO_ANSWER, State.BUSY, State.TECHNICAL_FAILURE, State.CANCELLED, State.OPTED_OUT}
LIVE = {State.CONNECTED, State.GREETING, State.PERMISSION_TO_CONTINUE, State.NEEDS_DISCOVERY, State.PRODUCT_EXPLANATION, State.OBJECTION_HANDLING, State.DEMO_INVITATION, State.HUMAN_HANDOFF, State.FOLLOWUP_SCHEDULING}

# Transitions available from every non-terminal state (safety paths)
_UNIVERSAL = {State.CANCELLED, State.TECHNICAL_FAILURE}
_UNIVERSAL_LIVE = {State.OPTED_OUT, State.HUMAN_HANDOFF, State.FOLLOWUP_SCHEDULING, State.COMPLETED}

TRANSITIONS: dict[State, set[State]] = {
    State.ELIGIBILITY_CHECK: {State.CALL_AUTHORIZATION},
    State.CALL_AUTHORIZATION: {State.DIAL_REQUEST},
    State.DIAL_REQUEST: {State.DIALING, State.NO_ANSWER, State.BUSY},
    State.DIALING: {State.RINGING, State.CONNECTED, State.NO_ANSWER, State.BUSY},
    State.RINGING: {State.CONNECTED, State.NO_ANSWER, State.BUSY},
    State.CONNECTED: {State.GREETING},
    State.GREETING: {State.PERMISSION_TO_CONTINUE},
    State.PERMISSION_TO_CONTINUE: {State.NEEDS_DISCOVERY, State.PRODUCT_EXPLANATION},
    State.NEEDS_DISCOVERY: {State.PRODUCT_EXPLANATION, State.OBJECTION_HANDLING},
    State.PRODUCT_EXPLANATION: {State.OBJECTION_HANDLING, State.DEMO_INVITATION, State.NEEDS_DISCOVERY},
    State.OBJECTION_HANDLING: {State.PRODUCT_EXPLANATION, State.DEMO_INVITATION, State.NEEDS_DISCOVERY},
    State.DEMO_INVITATION: {State.OBJECTION_HANDLING},
    State.HUMAN_HANDOFF: set(),
    State.FOLLOWUP_SCHEDULING: set(),
}
for _s in list(TRANSITIONS):
    if _s not in TERMINAL:
        TRANSITIONS[_s] |= _UNIVERSAL
    if _s in LIVE:
        TRANSITIONS[_s] |= _UNIVERSAL_LIVE
for _t in TERMINAL:
    TRANSITIONS[_t] = set()


class InvalidTransition(RuntimeError):
    pass


@dataclass
class Transition:
    from_state: State
    to_state: State
    reason: str
    at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ConversationContext:
    """Safety facts the state machine consults. These come from the backend, never from the model."""

    consent_ok: bool = True
    emergency_stop: bool = False
    opted_out: bool = False
    authorized: bool = False


class ConversationStateMachine:
    def __init__(self, initial: State = State.ELIGIBILITY_CHECK) -> None:
        self.state = initial
        self.history: list[Transition] = []

    def can(self, to: State) -> bool:
        return to in TRANSITIONS.get(self.state, set())

    def transition(self, to: State, *, reason: str = "", ctx: ConversationContext | None = None) -> Transition:
        ctx = ctx or ConversationContext()
        if ctx.emergency_stop and to not in (State.CANCELLED, State.TECHNICAL_FAILURE):
            to, reason = State.CANCELLED, f"emergency_stop ({reason})"
            if self.state in TERMINAL:
                raise InvalidTransition(f"{self.state} is terminal")
        elif ctx.opted_out and to not in (State.OPTED_OUT, State.CANCELLED, State.TECHNICAL_FAILURE):
            if self.state in LIVE:
                to, reason = State.OPTED_OUT, f"prospect opted out ({reason})"
            else:
                raise InvalidTransition("contact has opted out; only cancellation is allowed")
        if to == State.CALL_AUTHORIZATION and not ctx.consent_ok:
            raise InvalidTransition("consent/eligibility check failed")
        if to == State.DIAL_REQUEST and not ctx.authorized:
            raise InvalidTransition("call not authorized by operator")
        if not self.can(to):
            raise InvalidTransition(f"cannot transition {self.state} -> {to}")
        tr = Transition(self.state, to, reason)
        self.history.append(tr)
        self.state = to
        return tr

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL

    @property
    def is_live(self) -> bool:
        return self.state in LIVE
