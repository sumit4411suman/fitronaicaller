"""Approved, concise Hindi/English script lines per state. Prices are inserted ONLY from approved knowledge
entries passed in by the engine - the templates never hard-code numbers."""

from __future__ import annotations

from sellagent_ai.conversation.states import State

SCRIPTS: dict[State, dict[str, str]] = {
    State.GREETING: {
        "en": "Namaste, this is an automated AI assistant calling on behalf of FITRON, gym accounting software. Am I speaking with {contact_person} from {business_name}?",
        "hi": "नमस्ते, मैं FITRON जिम अकाउंटिंग सॉफ़्टवेयर की ओर से एक स्वचालित AI सहायक बोल रहा हूँ। क्या मेरी बात {business_name} से {contact_person} जी से हो रही है?",
    },
    State.PERMISSION_TO_CONTINUE: {
        "en": "Do you have two minutes to hear how FITRON handles gym accounting? If not, I can call back or stop entirely, your choice.",
        "hi": "क्या आपके पास दो मिनट हैं? मैं बताना चाहूँगा कि FITRON जिम की अकाउंटिंग कैसे संभालता है। अगर अभी समय नहीं है तो मैं बाद में कॉल कर सकता हूँ या बिल्कुल बंद कर सकता हूँ, जैसा आप चाहें।",
    },
    State.NEEDS_DISCOVERY: {
        "en": "How do you currently manage member payments and accounts at your gym? Is it on paper, a spreadsheet, or software?",
        "hi": "अभी आप अपने जिम में मेंबर पेमेंट और हिसाब-किताब कैसे संभालते हैं? कागज़ पर, एक्सेल में, या किसी सॉफ़्टवेयर से?",
    },
    State.PRODUCT_EXPLANATION: {
        "en": "FITRON is gym accounting software sold as a monthly subscription. {pricing_line} I can only share confirmed details; for anything else our team can follow up.",
        "hi": "FITRON जिम के लिए अकाउंटिंग सॉफ़्टवेयर है, जो मासिक सब्सक्रिप्शन पर मिलता है। {pricing_line} मैं केवल पुष्टि की गई जानकारी साझा कर सकता हूँ; बाकी के लिए हमारी टीम संपर्क करेगी।",
    },
    State.OBJECTION_HANDLING: {
        "en": "I understand. {objection_line} Would a short demo with our team help you decide?",
        "hi": "मैं समझता हूँ। {objection_line} क्या हमारी टीम के साथ एक छोटा डेमो आपको निर्णय लेने में मदद करेगा?",
    },
    State.DEMO_INVITATION: {
        "en": "Would you like a short demo with a FITRON team member? Which day and time suits you?",
        "hi": "क्या आप FITRON टीम के किसी सदस्य के साथ एक छोटा डेमो लेना चाहेंगे? कौन सा दिन और समय आपके लिए ठीक रहेगा?",
    },
    State.HUMAN_HANDOFF: {
        "en": "I will have a FITRON team member call you back to answer that properly. Thank you for your time.",
        "hi": "मैं FITRON टीम के किसी सदस्य से आपको वापस कॉल करवाता हूँ ताकि वे ठीक से जवाब दे सकें। आपके समय के लिए धन्यवाद।",
    },
    State.FOLLOWUP_SCHEDULING: {
        "en": "No problem. When would be a better time for a follow-up call?",
        "hi": "कोई बात नहीं। फ़ॉलो-अप कॉल के लिए कौन सा समय बेहतर रहेगा?",
    },
    State.OPTED_OUT: {
        "en": "Understood. I will remove your number from our calling list right away. Sorry for the disturbance, and have a good day.",
        "hi": "समझ गया। मैं आपका नंबर अभी हमारी कॉलिंग सूची से हटा देता हूँ। परेशानी के लिए क्षमा करें, आपका दिन शुभ हो।",
    },
    State.COMPLETED: {
        "en": "Thank you for your time. Goodbye.",
        "hi": "आपके समय के लिए धन्यवाद। नमस्ते।",
    },
}

UNKNOWN_INFO = {
    "en": "I don't have confirmed information about that. I can arrange for a FITRON team member to follow up with you.",
    "hi": "इस बारे में मेरे पास पुष्टि की गई जानकारी नहीं है। मैं FITRON टीम के किसी सदस्य से आपको फ़ॉलो-अप करवा सकता हूँ।",
}

OBJECTIONS = {
    "price": {
        "en": "The price I can confirm is the approved list price I mentioned; I cannot offer anything beyond approved terms.",
        "hi": "मैं केवल बताई गई स्वीकृत लिस्ट प्राइस की पुष्टि कर सकता हूँ; स्वीकृत शर्तों से अलग कुछ ऑफ़र नहीं कर सकता।",
    },
    "busy": {"en": "I can call back at a time that suits you.", "hi": "मैं आपके सुविधाजनक समय पर वापस कॉल कर सकता हूँ।"},
    "already_have": {"en": "That's fine. If you ever want to compare, our team can show you FITRON.", "hi": "ठीक है। अगर कभी तुलना करना चाहें तो हमारी टीम आपको FITRON दिखा सकती है।"},
    "generic": {"en": "That's a fair point.", "hi": "आपकी बात सही है।"},
}

OPT_OUT_PHRASES = [
    "do not call", "don't call", "dont call", "stop calling", "remove my number", "not interested", "unsubscribe", "never call",
    "mat karo", "call mat karo", "phone mat karo", "nahi chahiye", "nahin chahiye", "band karo", "हटा दो", "कॉल मत", "फोन मत", "नहीं चाहिए", "बंद करो", "रुचि नहीं",
]
CALLBACK_PHRASES = ["call later", "call back", "later", "busy", "baad mein", "baad me", "abhi nahi", "अभी नहीं", "बाद में", "व्यस्त", "busy hoon"]
DEMO_PHRASES = ["demo", "show me", "dikhao", "डेमो", "दिखाओ", "try"]
HUMAN_PHRASES = ["talk to a person", "real person", "human", "manager", "insaan", "aadmi se", "किसी व्यक्ति", "इंसान"]


def line(state: State, lang: str, **kw: str) -> str:
    tpl = SCRIPTS.get(state, {}).get(lang) or SCRIPTS.get(state, {}).get("en", "")
    try:
        return tpl.format(**{"contact_person": "", "business_name": "", "pricing_line": "", "objection_line": "", **kw}).replace("  ", " ").strip()
    except KeyError:
        return tpl


# ------------------------------------------------------------------ persona support
# Hindi verbs agree with the speaker's gender. The approved lines above are written in the masculine form; a female
# persona speaks them in the feminine form. Ordered longest-first so compound forms convert before their parts.
_HI_FEMININE = [
    ("बोल रहा हूँ", "बोल रही हूँ"), ("कर सकता हूँ", "कर सकती हूँ"), ("समझ नहीं पाया", "समझ नहीं पाई"), ("सुन नहीं पाया", "सुन नहीं पाई"),
    ("हटा देता हूँ", "हटा देती हूँ"), ("करवाता हूँ", "करवाती हूँ"), ("समझता हूँ", "समझती हूँ"), ("चाहूँगा", "चाहूँगी"),
    ("कर रहा हूँ", "कर रही हूँ"), ("बताता हूँ", "बताती हूँ"), ("लूँगा", "लूँगी"), ("रहा हूँ", "रही हूँ"), ("समझ गया", "समझ गई"), ("सकता हूँ", "सकती हूँ"), ("देता हूँ", "देती हूँ"),
]


def gendered(text: str, lang: str, gender: str) -> str:
    if lang != "hi" or gender != "female":
        return text
    for masc, fem in _HI_FEMININE:
        text = text.replace(masc, fem)
    return text


# Alternative wordings so the agent does not repeat itself word for word (same meaning, same approved content).
ALTERNATIVES: dict[State, dict[str, list[str]]] = {
    State.PERMISSION_TO_CONTINUE: {
        "en": ["Is this a good moment for a quick two-minute chat about FITRON? If not, I can call back or stop, whatever you prefer."],
        "hi": ["क्या अभी दो मिनट बात करना ठीक रहेगा? अगर नहीं, तो मैं बाद में कॉल कर सकता हूँ या यहीं रोक सकता हूँ, जैसा आप कहें।"],
    },
    State.NEEDS_DISCOVERY: {
        "en": ["Could you tell me how you keep track of member fees and renewals today?"],
        "hi": ["आप अभी मेंबर की फीस और रिन्यूअल का हिसाब कैसे रखते हैं?"],
    },
    State.DEMO_INVITATION: {
        "en": ["Would a short demo with our team be useful? Just tell me a day and time that works."],
        "hi": ["क्या हमारी टीम के साथ एक छोटा डेमो उपयोगी रहेगा? बस कोई सुविधाजनक दिन और समय बता दीजिए।"],
    },
    State.FOLLOWUP_SCHEDULING: {
        "en": ["Sure. What day and time would suit you for a call back?"],
        "hi": ["ज़रूर। आपको वापस कॉल के लिए कौन-सा दिन और समय ठीक रहेगा?"],
    },
}

# Persona-aware lines used when a conversational cue calls for a different response than the default script.
CUE_LINES = {
    "busy": {"en": "No problem, I'll keep it short. When would be a better time for a quick call back?", "hi": "कोई बात नहीं, मैं समय नहीं लूँगा। आपको वापस कॉल के लिए कौन-सा समय ठीक रहेगा?"},
    "existing_software": {"en": "That's helpful to know. What would you most like to improve in how you manage {tool} today?", "hi": "यह जानकर अच्छा लगा। अभी {tool} से काम करने में आप सबसे ज़्यादा क्या बेहतर करना चाहेंगे?"},
    "end_call": {"en": "Thank you for your time. Have a good day. Goodbye.", "hi": "आपके समय के लिए धन्यवाद। आपका दिन शुभ हो। नमस्ते।"},
}

SIMPLER = {
    State.GREETING: {"en": "I'm an AI assistant calling from FITRON, a gym accounting software. Am I speaking with the gym owner?", "hi": "मैं FITRON की ओर से एक AI सहायक हूँ। FITRON जिम का हिसाब रखने का सॉफ़्टवेयर है। क्या मेरी बात जिम के मालिक से हो रही है?"},
    State.PERMISSION_TO_CONTINUE: {"en": "Simply put: can we talk for two minutes now? Yes or no is fine.", "hi": "सीधी बात: क्या हम अभी दो मिनट बात कर सकते हैं? हाँ या नहीं बोल दीजिए।"},
    State.NEEDS_DISCOVERY: {"en": "I mean: do you note member payments on paper, in Excel, or in an app?", "hi": "मेरा मतलब है: आप मेंबर का पेमेंट कागज़ पर, एक्सेल में, या किसी ऐप में लिखते हैं?"},
    State.PRODUCT_EXPLANATION: {"en": "In short: FITRON is software that keeps your gym's member fees and accounts in one place, paid monthly.", "hi": "छोटे में: FITRON एक सॉफ़्टवेयर है जो आपके जिम की मेंबर फीस और हिसाब एक जगह रखता है, और इसका मासिक शुल्क है।"},
    State.OBJECTION_HANDLING: {"en": "Let me put it simply: I can only share confirmed details, and our team can answer anything else.", "hi": "आसान शब्दों में: मैं सिर्फ़ पुष्टि की गई जानकारी बता सकता हूँ, बाकी हमारी टीम बताएगी।"},
    State.DEMO_INVITATION: {"en": "I'm asking if you'd like someone from FITRON to show you the software. Would you like that?", "hi": "मैं पूछ रहा हूँ कि क्या आप चाहेंगे कि FITRON से कोई आपको सॉफ़्टवेयर दिखाए?"},
}

ACKS = {
    "interest": {"en": "Great.", "hi": "बहुत बढ़िया।"},
    "hesitation": {"en": "No pressure at all.", "hi": "कोई दबाव नहीं है।"},
    "impatient": {"en": "I'll be quick.", "hi": "मैं जल्दी बताता हूँ।"},
}
