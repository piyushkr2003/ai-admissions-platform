"""Response templates (docs/tasks/006 section 60).

There is no LLM system prompt in the default deterministic pipeline -
these functions are the "prompt management" equivalent: the single,
controlled place natural-language phrasing comes from. Every value
placeholder is filled from a verified tool/database result, never
invented here.

Full localization is out of scope for this task; English is complete
and Hindi/Hinglish/Kannada variants are provided for the most common
exchanges (greeting, fees, eligibility, scholarship, escalation,
no-answer) as proof the language-routing architecture works end-to-end.
Anything without a translated variant falls back to English rather than
mixing languages awkwardly - this is a documented limitation, not a bug.

Kannada ("kn") is selection-only: unlike Hindi/Hinglish, there is no
detect_language() heuristic for it (see app/agent/language.py) - it is
only ever set on AgentState.language via an explicit, locked language
selection (docs/voice.md "Language Selection"), never inferred from
message text.
"""
from __future__ import annotations


def _pick(language: str, en: str, hi: str | None = None, hinglish: str | None = None, kn: str | None = None) -> str:
    if language == "hi" and hi:
        return hi
    if language == "hinglish" and hinglish:
        return hinglish
    if language == "kn" and kn:
        return kn
    return en


def greeting(language: str, agent_name: str, college_name: str) -> str:
    return _pick(
        language,
        en=f"Hi! I'm {agent_name} from {college_name}. I can help with courses, eligibility, fees, scholarships, and booking a counselor appointment. How can I help?",
        hi=f"नमस्ते! मैं {college_name} से {agent_name} हूँ। मैं कोर्स, पात्रता, फीस, छात्रवृत्ति और काउंसलर अपॉइंटमेंट में मदद कर सकता हूँ।",
        hinglish=f"Hi! Main {agent_name} hoon, {college_name} se. Courses, eligibility, fees, scholarship, ya counselor appointment - kisme help chahiye?",
        kn=f"ನಮಸ್ಕಾರ! ನಾನು {college_name} ಕಾಲೇಜಿನ {agent_name}. ಕೋರ್ಸ್‌ಗಳು, ಅರ್ಹತೆ, ಶುಲ್ಕ, ವಿದ್ಯಾರ್ಥಿವೇತನ ಮತ್ತು ಕೌನ್ಸಲರ್ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕ್ ಮಾಡಲು ನಾನು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ. ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?",
    )


def course_info(language: str, name: str, duration_years, degree_type: str | None, description: str | None) -> str:
    base = f"{name} is a {duration_years}-year {degree_type or 'program'}."
    if description:
        base += f" {description}"
    return base


def eligibility_eligible(language: str, course_name: str) -> str:
    return _pick(
        language,
        en=f"Based on the configured eligibility criteria, you meet the basic eligibility requirements for {course_name}.",
        hi=f"कॉन्फ़िगर की गई पात्रता शर्तों के अनुसार, आप {course_name} के लिए पात्र हैं।",
        hinglish=f"Configured eligibility criteria ke hisaab se, aap {course_name} ke liye eligible hain.",
        kn=f"ಕಾನ್ಫಿಗರ್ ಮಾಡಲಾದ ಅರ್ಹತಾ ಮಾನದಂಡಗಳ ಪ್ರಕಾರ, ನೀವು {course_name} ಗೆ ಅರ್ಹರಾಗಿದ್ದೀರಿ.",
    )


def eligibility_not_eligible(language: str, course_name: str, reasons: list[str]) -> str:
    reason_text = " ".join(reasons)
    return _pick(
        language,
        en=f"Based on the configured eligibility criteria, you do not currently meet the requirements for {course_name}. {reason_text}",
        hinglish=f"Configured criteria ke hisaab se, aap abhi {course_name} ke liye eligible nahi hain. {reason_text}",
        kn=f"ಕಾನ್ಫಿಗರ್ ಮಾಡಲಾದ ಅರ್ಹತಾ ಮಾನದಂಡಗಳ ಪ್ರಕಾರ, ನೀವು ಸದ್ಯಕ್ಕೆ {course_name} ಗೆ ಅರ್ಹರಲ್ಲ. {reason_text}",
    )


def eligibility_missing_info(language: str, missing: list[str]) -> str:
    fields = " and ".join(missing)
    return _pick(
        language,
        en=f"Sure, I can check that. Could you share your {fields}?",
        hinglish=f"Zaroor, check karta hoon. Aap apna {fields} bata sakte hain?",
        kn=f"ಖಂಡಿತ, ನಾನು ಪರಿಶೀಲಿಸುತ್ತೇನೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ {fields} ತಿಳಿಸುತ್ತೀರಾ?",
    )


def fee_info(language: str, course_name: str, annual_fee, academic_year: str | None, hostel_fee=None) -> str:
    year_text = f" for {academic_year}" if academic_year else ""
    year_text_kn = f" ({academic_year} ಶೈಕ್ಷಣಿಕ ವರ್ಷಕ್ಕೆ)" if academic_year else ""
    base = _pick(
        language,
        en=f"The current tuition fee for {course_name}{year_text} is ₹{annual_fee:,.0f} per year.",
        hinglish=f"{course_name} ka tuition fee{year_text} ₹{annual_fee:,.0f} per year hai.",
        kn=f"{course_name} ಕೋರ್ಸ್‌ಗೆ ಪ್ರಸ್ತುತ ವಾರ್ಷಿಕ ಬೋಧನಾ ಶುಲ್ಕ ₹{annual_fee:,.0f}{year_text_kn}.",
    )
    if hostel_fee:
        base += _pick(
            language,
            en=f" Hostel fees are ₹{hostel_fee:,.0f} per year if you need accommodation.",
            hinglish=f" Hostel chahiye toh uska fee ₹{hostel_fee:,.0f} per year hai.",
            kn=f" ವಸತಿನಿಲಯ ಬೇಕಿದ್ದರೆ, ಅದರ ಶುಲ್ಕ ವರ್ಷಕ್ಕೆ ₹{hostel_fee:,.0f}.",
        )
    return base


def fee_unavailable(language: str) -> str:
    return _pick(
        language,
        en="I don't have a verified fee figure for that course right now. I can connect you with an admissions counselor.",
        hinglish="Abhi mere paas is course ka verified fee nahi hai. Main aapko admissions counselor se connect kar sakta hoon.",
        kn="ಈ ಕೋರ್ಸ್‌ಗೆ ಸದ್ಯಕ್ಕೆ ಪರಿಶೀಲಿತ ಶುಲ್ಕ ಮಾಹಿತಿ ನನ್ನ ಬಳಿ ಇಲ್ಲ. ನಾನು ನಿಮ್ಮನ್ನು ಅಡ್ಮಿಷನ್ಸ್ ಕೌನ್ಸಲರ್‌ಗೆ ಸಂಪರ್ಕಿಸಬಲ್ಲೆ.",
    )


def scholarship_info(language: str, scholarships: list[dict]) -> str:
    if len(scholarships) == 1:
        s = scholarships[0]
        benefit = f"{s['percentage']}%" if s.get("percentage") else (f"₹{s['amount']:,.0f}" if s.get("amount") else "a benefit")
        return _pick(
            language,
            en=f"Yes - the {s['name']} offers {benefit} based on the configured eligibility criteria. I can't guarantee approval, but you're welcome to apply.",
            hinglish=f"Haan - {s['name']} mein {benefit} milta hai configured criteria ke hisaab se. Approval guaranteed nahi hai, lekin aap apply kar sakte hain.",
            kn=f"ಹೌದು - ಕಾನ್ಫಿಗರ್ ಮಾಡಿದ ಅರ್ಹತಾ ಮಾನದಂಡಗಳ ಪ್ರಕಾರ {s['name']} ಅಡಿಯಲ್ಲಿ {benefit} ಸಿಗುತ್ತದೆ. ಅನುಮೋದನೆ ಖಚಿತವಿಲ್ಲ, ಆದರೆ ನೀವು ಅರ್ಜಿ ಸಲ್ಲಿಸಬಹುದು.",
        )
    names = ", ".join(s["name"] for s in scholarships)
    return f"There are a few scholarships available: {names}. I can share details on any of them."


def scholarship_unavailable(language: str) -> str:
    return _pick(
        language,
        en="I don't see a configured scholarship for that course right now. I can connect you with a counselor to check current options.",
    )


def required_documents(language: str, documents: list[str]) -> str:
    listing = "; ".join(documents)
    return _pick(
        language,
        en=f"You'll need: {listing}.",
        hinglish=f"Aapko ye documents chahiye honge: {listing}.",
        kn=f"ನಿಮಗೆ ಇವು ಬೇಕಾಗುತ್ತವೆ: {listing}.",
    )


def admission_dates(language: str, dates: list[dict]) -> str:
    parts = [f"{d['title']}: {d['date']}" for d in dates]
    return "Key dates - " + "; ".join(parts) + "."


def admission_process(language: str, process_text: str | None) -> str:
    if process_text:
        return process_text
    return "Please apply online, complete the required steps, submit documents, and pay the admission fee to confirm your seat."


def no_verified_info(language: str) -> str:
    return _pick(
        language,
        en="I don't have verified information about that yet. I can connect you with an admissions counselor who can help.",
        hinglish="Abhi iske baare mein mere paas verified information nahi hai. Main aapko admissions counselor se connect kar sakta hoon.",
        kn="ಇದರ ಬಗ್ಗೆ ನನ್ನ ಬಳಿ ಇನ್ನೂ ಪರಿಶೀಲಿತ ಮಾಹಿತಿ ಇಲ್ಲ. ನಾನು ನಿಮ್ಮನ್ನು ಸಹಾಯ ಮಾಡಬಲ್ಲ ಅಡ್ಮಿಷನ್ಸ್ ಕೌನ್ಸಲರ್‌ಗೆ ಸಂಪರ್ಕಿಸಬಲ್ಲೆ.",
    )


def out_of_scope(language: str) -> str:
    return "I'm focused on admissions-related questions for prospective students. For that, I can connect you with our admissions/student services team."


def cross_tenant_refusal(language: str) -> str:
    return "I can help with admissions information for this college, but I can't provide information belonging to another institution."


def injection_refusal(language: str) -> str:
    return "I can't share internal instructions or another institution's information, but I'm happy to help with admissions questions for this college."


def counselor_slots(language: str, slots: list[dict]) -> str:
    if not slots:
        return "I couldn't find an available counselor slot right now. I can create a request and have someone follow up with you."
    from datetime import datetime as _dt

    top = slots[0]
    try:
        friendly = _dt.fromisoformat(top["start_time"]).strftime("%a, %b %d at %I:%M %p").replace(" 0", " ")
    except ValueError:
        friendly = top["start_time"]
    return f"I have a slot available with {top['counselor_name']} at {friendly}. Would you like me to book it?"


def appointment_confirmed(language: str, counselor_name: str, start_time: str) -> str:
    return _pick(
        language,
        en=f"Done - your counseling appointment with {counselor_name} is confirmed for {start_time}.",
        hinglish=f"Ho gaya - aapka appointment {counselor_name} ke saath {start_time} ke liye confirm ho gaya hai.",
        kn=f"ಆಯಿತು - {counselor_name} ಅವರೊಂದಿಗಿನ ನಿಮ್ಮ ಕೌನ್ಸಲಿಂಗ್ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ {start_time} ಕ್ಕೆ ದೃಢಪಟ್ಟಿದೆ.",
    )


def appointment_failed(language: str) -> str:
    return "I wasn't able to complete that booking - the slot may have just been taken. I can check the next available times for you."


def application_draft_created(language: str, course_name: str) -> str:
    return _pick(
        language,
        en=f"I've created your draft application for {course_name}. It still needs to be completed and submitted - it has not been submitted yet.",
        hinglish=f"{course_name} ke liye aapka draft application ban gaya hai. Ye abhi submit nahi hua hai - poora karke submit karna hoga.",
        kn=f"{course_name} ಗಾಗಿ ನಿಮ್ಮ ಡ್ರಾಫ್ಟ್ ಅರ್ಜಿ ರಚಿಸಲಾಗಿದೆ. ಇದನ್ನು ಇನ್ನೂ ಪೂರ್ಣಗೊಳಿಸಿ ಸಲ್ಲಿಸಬೇಕಾಗಿದೆ - ಇದು ಇನ್ನೂ ಸಲ್ಲಿಕೆಯಾಗಿಲ್ಲ.",
    )


def application_status(language: str, status: str, next_steps: list[str]) -> str:
    steps = " ".join(next_steps)
    return f"Your application status is: {status}. {steps}".strip()


def escalation_created(language: str) -> str:
    return _pick(
        language,
        en="I've created a request for an admissions counselor to reach out to you.",
        hinglish="Maine admissions counselor ke liye ek request bana di hai, woh aapse contact karenge.",
        kn="ಅಡ್ಮಿಷನ್ಸ್ ಕೌನ್ಸಲರ್ ನಿಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸಲು ನಾನು ಒಂದು ವಿನಂತಿಯನ್ನು ರಚಿಸಿದ್ದೇನೆ.",
    )


def unknown_fallback(language: str, agent_name: str) -> str:
    return f"I'm {agent_name}, here to help with admissions questions - courses, eligibility, fees, scholarships, documents, or booking a counselor. What would you like to know?"


_LANGUAGE_RESPONSE_INSTRUCTIONS = {
    "en": "Respond in English.",
    "hi": (
        "Respond in natural, conversational Hindi (Devanagari script). If the student's message mixes "
        "Hindi and English, you may naturally respond in Hinglish where that reads more naturally - "
        "do not force pure Hindi if it would sound stiff."
    ),
    "hinglish": "Respond in natural Hinglish (mixed Hindi-English, Latin script).",
    "kn": "Respond in natural, conversational Kannada (Kannada script).",
}


def open_ended_system_prompt(college_name: str, agent_name: str, language: str = "en") -> str:
    """System prompt for the ONE bounded LLM call site
    (AgentOrchestrator._open_ended_reply, Task 016) - used only when the
    deterministic intent detector found no matching admissions topic at
    all. Every fact-bearing intent is handled entirely by tools/templates
    above and never reaches an LLM.

    `language` is passed in explicitly from the conversation's already-
    resolved AgentState.language (user-selected or detected) - the LLM is
    told the answer directly rather than asked to infer it, so it never
    spends its limited local-model reasoning/tokens on language
    identification (docs/voice.md "Language Selection")."""
    language_instruction = _LANGUAGE_RESPONSE_INSTRUCTIONS.get(language, _LANGUAGE_RESPONSE_INSTRUCTIONS["en"])
    return (
        f"You are {agent_name}, a virtual AI admissions assistant for {college_name}. "
        "You are having a short, natural spoken conversation with a prospective student or parent "
        "who just said something you don't have a specific admissions answer for. "
        f"{language_instruction} "
        "Respond in one or two short, natural sentences. "
        "You must NEVER state or imply any specific fee, discount, scholarship amount, eligibility "
        "determination, admission deadline, document requirement, appointment time, or application "
        "status - you do not have that information here. "
        "You must NEVER claim any action (booking, application, payment) succeeded. "
        "You must identify as an AI/virtual assistant if asked, never as a human. "
        "Acknowledge what the student said, gently steer the conversation toward courses, eligibility, "
        "fees, scholarships, required documents, admission dates, counselor appointments, or the "
        "application process, or offer to connect them with the admissions team if you can't help."
    )
