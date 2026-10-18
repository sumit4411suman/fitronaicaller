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
