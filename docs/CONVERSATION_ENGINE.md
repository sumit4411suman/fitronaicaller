# Conversation engine

## States (20)
eligibility_check -> call_authorization -> dial_request -> dialing -> ringing -> connected -> greeting ->
permission_to_continue -> needs_discovery -> product_explanation <-> objection_handling -> demo_invitation ->
followup_scheduling | human_handoff -> completed; terminal side exits: no_answer, busy, technical_failure, cancelled, opted_out.

Guards: `call_authorization` needs a passing eligibility result; `dial_request` needs operator authorisation; emergency stop
forces `cancelled` from any non-terminal state; an opted-out prospect forces `opted_out` from any live state; terminal
states have no exits; every other transition not in the table raises `InvalidTransition`.

## Turn processing (`ConversationEngine.respond`)
1. Detect language (Devanagari / romanised-Hindi lexicon) unless manually fixed; `auto` follows the prospect.
2. Classify intent by phrase lists: opt_out, human, demo, callback, price, affirm, negative, question.
3. Safety first: emergency stop -> cancel; opt-out phrases -> `opted_out` with the apology line; the backend then adds the
   number to the suppression list and withdraws consent.
4. Advance the state machine and pick the approved script line; prices are injected only from approved `pricing` facts and
   the reply carries their `kb:` references.
5. Optionally ask the local LLM to rephrase (approved facts in the prompt, instructions to treat them as data); accept only
   if `guardrails.check_reply` passes, otherwise keep the script line.
6. Classify outcome (`demo_scheduled`, `callback_requested`, `human_handoff`, `opted_out`, ...) and request a follow-up.

## Guardrails
* Every rupee amount and percentage must match an approved structured fact (rounded values allowed, e.g. Rs 999.50 -> Rs 1,000).
* Forbidden claims: guarantees, testimonials, integrations, support commitments, revenue claims, availability dates,
  unverified features, "free forever".
* Greeting must name FITRON and disclose the automated assistant.
* No pressure after opt-out.

## Scripts
`sellagent_ai/conversation/scripts.py` holds concise Hindi and English lines per state, objection snippets and the
"no confirmed information" fallback. The desktop Sales Script Editor stores overrides as a knowledge document.
