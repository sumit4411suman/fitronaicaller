# FITRON knowledge base

Seeded on first run (English and Hindi versions):

| Entry | Category | Status at seed | Structured fields |
| --- | --- | --- | --- |
| What FITRON is | product | approved | product, type, model |
| Professional plan list price Rs 1,999 per month | pricing | approved | plan, price_inr=1999, period=month |
| First-100-customers offer (1 month free + 50% off, approx Rs 1,000/month) | offer | **pending_review** | free_months, discount_percent=50, discounted_price_inr_approx=1000, duration/eligibility/dates/terms = TO BE CONFIGURED |
| What the agent must not claim | compliance | approved | policy |

Workflow: create or import (untrusted, screened) -> review flags -> approve (acknowledge flags if any) -> retrievable.
Supersede creates version n+1 pending review; approving it marks the old version `superseded`. `expires_at` and
`effective_from` are enforced at retrieval time; `expire_outdated` flips expired approved docs to `expired`.

The offer must be configured (duration, eligibility, start/end, terms) in its structured fields and approved by an
authorised user before the agent can mention it; until then retrieval excludes it and guardrails reject "50%" or
"Rs 1,000" in any reply because no approved fact carries those numbers.
