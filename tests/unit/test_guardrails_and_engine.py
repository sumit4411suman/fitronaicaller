import pytest
from sellagent_ai.conversation import (
    ConversationContext,
    ConversationEngine,
    ConversationStateMachine,
    KnowledgeFact,
    State,
)
from sellagent_ai.guardrails import check_reply
from sellagent_ai.llm import ChatMessage, NullProvider

pytestmark = pytest.mark.automated

FACTS = [
    KnowledgeFact("kb:1#v1", "price", "pricing", "Professional plan is ₹1,999 per month.", {"plan": "Professional", "price_inr": 1999, "period": "month"}),
    KnowledgeFact("kb:2#v1", "what", "product", "FITRON is gym accounting software.", {"product": "FITRON"}),
]


def test_approved_price_passes():
    assert check_reply("The Professional plan is ₹1,999 per month.", approved_facts=[f.structured for f in FACTS], state="product_explanation").allowed


@pytest.mark.parametrize("text,label", [
    ("It costs only ₹499 per month", "unapproved amount"),
    ("Get 70% off today", "unapproved percentage"),
    ("We guarantee your revenue will double", "guarantee"),
    ("It integrates with WhatsApp and Tally", "integration"),
    ("Our customers say it is the best, 5-star rated", "testimonial"),
    ("We offer 24/7 dedicated support", "support_commitment"),
])
def test_unsupported_claims_rejected(text, label):
    r = check_reply(text, approved_facts=[f.structured for f in FACTS], state="product_explanation")
    assert not r.allowed and any(label in v for v in r.violations)


def test_greeting_requires_disclosure():
    assert not check_reply("Hello, how are you today?", approved_facts=[], state="greeting").allowed
    assert check_reply("Namaste, this is an automated AI assistant calling on behalf of FITRON.", approved_facts=[], state="greeting").allowed


def test_rounded_offer_price_allowed():
    facts = [{"discount_percent": 50, "discounted_price_inr_approx": 1000, "base_price_inr": 1999}]
    assert check_reply("50% off, about ₹1,000 per month", approved_facts=facts, state="product_explanation").allowed


class FakeLLM:
    name = "fake"

    def __init__(self, reply: str):
        self.reply = reply

    def available(self):
        return True, "ok"

    def list_models(self):
        return [{"name": "fake"}]

    def stream(self, messages: list[ChatMessage], *, model, temperature=0.3, max_tokens=256, cancel=None, timeout=60.0):
        yield self.reply


def _run(engine: ConversationEngine, utterances: list[str | None], ctx: ConversationContext | None = None, lang="auto"):
    sm = ConversationStateMachine(State.CONNECTED)
    ctx = ctx or ConversationContext(authorized=True)
    turns = []
    for u in utterances:
        turns.append(engine.respond(sm, u, facts=FACTS, ctx=ctx, preferred_language=lang, contact_person="Rahul", business_name="Power Gym"))
        if sm.is_terminal:
            break
    return sm, turns


def test_script_only_flow_english_to_demo():
    eng = ConversationEngine(NullProvider(), use_llm=False)
    sm, turns = _run(eng, [None, "yes", "we use excel", "how much?", "ok send demo", "tomorrow 5pm", None], lang="en")
    assert "FITRON" in turns[0].agent_text and "automated" in turns[0].agent_text.lower()
    assert any("₹1,999" in t.agent_text for t in turns) and any(t.knowledge_refs == ["kb:1#v1"] for t in turns)
    assert sm.state == State.COMPLETED and turns[-1].outcome in ("demo_scheduled", "callback_requested")


def test_hindi_flow_and_opt_out():
    eng = ConversationEngine(NullProvider(), use_llm=False)
    sm, turns = _run(eng, [None, "haan bataiye", "mujhe call mat karo"], lang="auto")
    assert sm.state == State.OPTED_OUT and turns[-1].outcome == "opted_out" and "सूची" in turns[-1].agent_text


def test_llm_output_failing_guardrails_falls_back_to_script():
    eng = ConversationEngine(FakeLLM("Only ₹299 and we guarantee results with WhatsApp integration!"), model="fake")
    sm, turns = _run(eng, [None, "yes", "excel", "price?"], lang="en")
    price_turn = [t for t in turns if "₹" in t.agent_text][0]
    assert price_turn.source == "script" and "₹1,999" in price_turn.agent_text and "₹299" not in price_turn.agent_text


def test_llm_output_passing_guardrails_is_used():
    eng = ConversationEngine(FakeLLM("FITRON is gym accounting software and the Professional plan is ₹1,999 per month."), model="fake")
    sm, turns = _run(eng, [None, "yes", "excel"], lang="en")
    assert turns[-1].source == "llm"


def test_emergency_stop_cancels_immediately():
    eng = ConversationEngine(NullProvider(), use_llm=False)
    sm, turns = _run(eng, [None], ctx=ConversationContext(authorized=True, emergency_stop=True))
    assert sm.state == State.CANCELLED and turns[0].outcome == "cancelled"


def test_unknown_question_gets_no_confirmed_info():
    eng = ConversationEngine(NullProvider(), use_llm=False)
    sm, turns = _run(eng, [None, "yes", "excel", "does it do biometric attendance?"], lang="en")
    assert "confirmed information" in turns[-1].agent_text or "FITRON is gym accounting software" in turns[-1].agent_text
    assert not any("biometric" in t.agent_text.lower() for t in turns)
