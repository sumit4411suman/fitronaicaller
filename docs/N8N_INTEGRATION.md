# Optional n8n automation for SELL AGENT

Status date: 2026-10-19. **Optional.** SELL AGENT works fully without n8n; this only adds scheduling/automation
around the **local** SELL AGENT API. n8n never touches audio or the conversation loop — the Python engine owns
that.

## Rules (enforced by SELL AGENT, not by n8n)

- n8n calls only the **documented local API** (`http://127.0.0.1:8765/api/v1/...`) with the local token. It gets
  no database access and no telephony access of its own.
- **No n8n workflow can bypass consent, eligibility, opt-out, quiet hours, suppression, or the emergency stop.**
  Those are checked inside the API/engine on every call-job and campaign action, regardless of caller. An n8n
  flow that asks to dial an ineligible or opted-out contact gets the same refusal the UI would.
- Outbound **promotional** autonomous calling stays disabled until the calling route and Indian compliance are
  approved (`docs/COMPLIANCE_INDIA.md`); n8n cannot turn that on.
- Keep n8n on the same machine / loopback; do not expose the SELL AGENT API to the network for it.

## Licensing

n8n Community Edition is under the **Sustainable Use License** (fair-code), not OSI open-source. It is fine for
your **own internal business use** and for **building an integration between your product and n8n**. It is **not**
fine to white-label n8n, resell it, or host it for others for money.
([n8n Sustainable Use License](https://docs.n8n.io/n8n-community-license/sustainable-use-license/),
[license FAQ](https://docs.n8n.io/n8n-community-license/community-license/license-faq/)). Because SELL AGENT keeps
n8n **optional and internal** (it automates your own campaigns; customers don't get an n8n instance), this use is
within the licence. If SELL AGENT is ever distributed to customers, **do not bundle n8n into the product** — keep
it an optional operator-side tool, or contact `license@n8n.io`. This is a summary, not legal advice.

## Good uses (all via the local API)

| Job | API it calls |
|---|---|
| Daily: surface follow-ups due today to the operator | `GET /api/v1/followups?until=<ISO>` |
| Nightly: pull campaign stats into a report/sheet | `GET /api/v1/campaigns/{id}/stats`, `GET /api/v1/reports/...` |
| After a call result: create a follow-up task | `POST /api/v1/followups` |
| Health watchdog / alert if the backend is down | `GET /api/v1/health/ping` |
| Scheduled campaign window open/close (human-assisted) | `POST /api/v1/campaigns/{id}/start` / `/pause` |

n8n should **read and schedule**, and let the operator and the engine make the calls — it should not try to drive
live audio.

## Sample workflow

`integrations/n8n/sellagent_followups.json` — a minimal, importable flow: every weekday morning it fetches
follow-ups due today and posts a digest to a notifier of your choice. Import it in n8n, set the
`SELLAGENT_TOKEN` credential/header and your notifier node, and enable it.

## Setup outline

1. Self-host n8n Community Edition on the same PC (Docker or npm), bound to localhost.
2. In SELL AGENT, mint a local API token (Settings) for n8n; store it as an n8n credential/header
   (`Authorization: Bearer <token>`).
3. Import the sample workflow, point its HTTP nodes at `http://127.0.0.1:8765`, set the notifier, enable.
4. Confirm a refused action (e.g. a follow-up for an opted-out contact) is rejected by the API — proof that n8n
   cannot bypass controls.
