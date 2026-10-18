"""AI sales persona: identity disclosure, feminine Hindi, cue-driven responses, memory, no repetition, and that
persona settings can never override approved facts or opt-out. Script mode (no LLM) so results are deterministic."""

from __future__ import annotations

from sellagent_ai.conversation import (
    ConversationContext,
    ConversationEngine,
    ConversationStateMachine,
    KnowledgeFact,
    State,
)
from sellagent_ai.persona import ConversationMemory, Persona, infer_cues

FACTS = [KnowledgeFact("kb:price#v1", "Professional plan", "pricing", "Professional plan: ₹1,999 per month.", {"price_inr": 1999, "plan": "Professional"})]
ENGINE = ConversationEngine(None, use_llm=False)


def _turn(sm, utterance, *, lang="en", persona=None, memory=None, ctx=None):  # type: ignore[no-untyped-def]
    persona = persona or Persona()
    memory = memory if memory is not None else ConversationMemory()
    if utterance:
        memory.observe("prospect", utterance)
    t = ENGINE.respond(sm, utterance, facts=FACTS, ctx=ctx or ConversationContext(authorized=True), preferred_language=lang, contact_person="Rahul", business_name="Power Gym", persona=persona, memory=memory)
    memory.observe("agent", t.agent_text)
    return t


def test_greeting_names_persona_and_discloses_ai_in_both_languages():
    en = _turn(ConversationStateMachine(State.CONNECTED), None)
    assert "Priya" in en.agent_text and "AI assistant" in en.agent_text
    hi = _turn(ConversationStateMachine(State.CONNECTED), None, lang="hi")
    assert "Priya" in hi.agent_text and "AI" in hi.agent_text
    assert "बोल रही हूँ" in hi.agent_text and "बोल रहा हूँ" not in hi.agent_text  # feminine first person


def test_custom_greeting_cannot_drop_ai_disclosure_or_invent_prices():
    p = Persona(greeting_en="Hi {contact_person}, quick call about FITRON for {business_name}.")
    t = _turn(ConversationStateMachine(State.CONNECTED), None, persona=p)
    assert t.agent_text.startswith("I'm Priya, an AI assistant") and "Rahul" in t.agent_text
    bad = Persona(greeting_en="Hello, I'm an AI assistant. FITRON is only ₹499 per month today!")
    t = _turn(ConversationStateMachine(State.CONNECTED), None, persona=bad)
    assert "₹499" not in t.agent_text  # guardrails reject unapproved prices whatever the persona says


def test_busy_owner_gets_short_callback_offer_not_a_pitch():
    t = _turn(ConversationStateMachine(State.PERMISSION_TO_CONTINUE), "I'm driving right now")
    assert t.state == State.FOLLOWUP_SCHEDULING and t.followup_requested and "busy" in t.cues
    assert "keep it short" in t.agent_text and "₹" not in t.agent_text


def test_confused_owner_gets_a_simpler_explanation_in_the_same_state():
    sm = ConversationStateMachine(State.PRODUCT_EXPLANATION)
    t = _turn(sm, "sorry, I didn't understand", lang="en")
    assert sm.state == State.PRODUCT_EXPLANATION and "In short" in t.agent_text
    hi = _turn(ConversationStateMachine(State.NEEDS_DISCOVERY), "मतलब? समझ नहीं आया", lang="hi")
    assert "मेरा मतलब" in hi.agent_text


def test_existing_software_asks_what_to_improve_then_moves_on_with_memory():
    sm, mem = ConversationStateMachine(State.NEEDS_DISCOVERY), ConversationMemory()
    t1 = _turn(sm, "we already use Excel for member fees", memory=mem)
    assert "excel" in t1.agent_text.lower() and "improve" in t1.agent_text and sm.state == State.NEEDS_DISCOVERY
    assert mem.current_tool == "excel" and "payment tracking" in mem.needs or "membership management" in mem.needs
    t2 = _turn(sm, "pending payments are hard to track", memory=mem)
    assert sm.state == State.PRODUCT_EXPLANATION and "₹1,999" in t2.agent_text  # approved price only
    assert "currently uses: excel" in mem.summary()


def test_owner_ending_the_call_gets_a_polite_close_and_opt_out_still_wins():
    sm = ConversationStateMachine(State.PRODUCT_EXPLANATION)
    t = _turn(sm, "ok thank you bye")
    assert sm.state == State.COMPLETED and "Goodbye" in t.agent_text and t.outcome == "not_interested"
    sm = ConversationStateMachine(State.PERMISSION_TO_CONTINUE)
    t = _turn(sm, "I'm busy, and don't call me again", persona=Persona(style="warm"))
    assert sm.state == State.OPTED_OUT and t.outcome == "opted_out"  # opt-out is checked before any persona logic


def test_interest_and_hesitation_get_acknowledged():
    t = _turn(ConversationStateMachine(State.PRODUCT_EXPLANATION), "sounds good, show me a demo")
    assert t.agent_text.startswith("Great.") and t.state == State.DEMO_INVITATION
    t = _turn(ConversationStateMachine(State.DEMO_INVITATION), "not sure, maybe")
    assert t.agent_text.startswith("No pressure at all.")


def test_no_word_for_word_repetition():
    mem = ConversationMemory()
    sm = ConversationStateMachine(State.PRODUCT_EXPLANATION)
    first = _turn(sm, "demo", memory=mem).agent_text
    sm2 = ConversationStateMachine(State.PRODUCT_EXPLANATION)
    second = _turn(sm2, "demo", memory=mem).agent_text
    assert first != second and sm2.state == State.DEMO_INVITATION


def test_persona_never_bypasses_safety_context():
    sm = ConversationStateMachine(State.PRODUCT_EXPLANATION)
    t = _turn(sm, "tell me more", ctx=ConversationContext(authorized=True, emergency_stop=True))
    assert sm.state == State.CANCELLED and t.agent_text == ""


def test_cue_inference_is_word_based_and_bilingual():
    assert {"busy"} <= infer_cues("abhi time nahi hai")
    assert {"price_concern"} <= infer_cues("बहुत महंगा है")
    assert {"confused"} <= infer_cues("matlab kya hai")
    assert infer_cues("") == set()
