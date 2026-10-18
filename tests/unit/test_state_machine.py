import pytest

from sellagent_ai.conversation import LIVE, TERMINAL, TRANSITIONS, ConversationContext, ConversationStateMachine, InvalidTransition, State

pytestmark = pytest.mark.automated


def test_all_twenty_states_present():
    assert len(State) == 20


def test_happy_path():
    sm = ConversationStateMachine()
    ctx = ConversationContext(consent_ok=True, authorized=True)
    for s in (State.CALL_AUTHORIZATION, State.DIAL_REQUEST, State.DIALING, State.RINGING, State.CONNECTED, State.GREETING, State.PERMISSION_TO_CONTINUE, State.NEEDS_DISCOVERY, State.PRODUCT_EXPLANATION, State.DEMO_INVITATION, State.FOLLOWUP_SCHEDULING, State.COMPLETED):
        sm.transition(s, ctx=ctx)
    assert sm.is_terminal and len(sm.history) == 12


def test_invalid_transition_rejected():
    sm = ConversationStateMachine()
    with pytest.raises(InvalidTransition):
        sm.transition(State.CONNECTED, ctx=ConversationContext(authorized=True))


def test_consent_gate():
    sm = ConversationStateMachine()
    with pytest.raises(InvalidTransition):
        sm.transition(State.CALL_AUTHORIZATION, ctx=ConversationContext(consent_ok=False))


def test_authorization_gate():
    sm = ConversationStateMachine(State.CALL_AUTHORIZATION)
    with pytest.raises(InvalidTransition):
        sm.transition(State.DIAL_REQUEST, ctx=ConversationContext(authorized=False))


def test_opt_out_overrides_everything_live():
    sm = ConversationStateMachine(State.PRODUCT_EXPLANATION)
    tr = sm.transition(State.DEMO_INVITATION, ctx=ConversationContext(opted_out=True))
    assert tr.to_state == State.OPTED_OUT and sm.is_terminal


def test_emergency_stop_forces_cancel():
    sm = ConversationStateMachine(State.RINGING)
    sm.transition(State.CONNECTED, ctx=ConversationContext(emergency_stop=True))
    assert sm.state == State.CANCELLED


def test_terminal_states_have_no_exits():
    for t in TERMINAL:
        assert TRANSITIONS[t] == set()
        with pytest.raises(InvalidTransition):
            ConversationStateMachine(t).transition(State.COMPLETED)


def test_live_states_can_opt_out_and_handoff():
    for s in LIVE:
        assert State.OPTED_OUT in TRANSITIONS[s] and State.HUMAN_HANDOFF in TRANSITIONS[s]
