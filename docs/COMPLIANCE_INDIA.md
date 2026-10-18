# SELL AGENT - India Compliance Research Notes (Telecom and Privacy)

Status: engineering compliance notes, not legal advice. Research date: 2026-10-18.
Scope: outbound promotional voice calls to Indian gym owners (B2B leads) from a Windows desktop + Android companion on a Jio consumer SIM, selling FITRON gym accounting software.

Retrieval caveat: `trai.gov.in`, `pib.gov.in`, `jio.com`, `indiacode.nic.in`, `meity.gov.in` and most Indian law-firm sites were not resolvable from the research container. Where a claim could only be confirmed through search-engine summaries of those documents it is marked "(search summary)". Where no source could be read it is marked UNVERIFIED. Clause numbers are given only where a source quoted them.

## 1. TRAI TCCCPR 2018 and amendments (2025, 2026)

Primary instrument: Telecom Commercial Communications Customer Preference Regulations, 2018 (notified 19 July 2018), gazette copy at https://www.trai.gov.in/sites/default/files/2024-09/RegulationUcc19072018.pdf (search summary, 2026-10-18; PDF not retrievable here). Consolidated and amended text index: https://trai.gov.in/tcccpr (UNVERIFIED, not retrievable).

### 1.1 Definitions (Regulation 2)

| Term | What the regulation says (as quoted by sources) | Source |
|---|---|---|
| Commercial Communication | "any voice call or message using telecommunication services, where the primary purpose is to inform about or advertise or solicit business for" goods, services, suppliers or business/investment opportunities (Reg. 2, clause (i) in the 2018 numbering) | indiankanoon.org/doc/60694660 and the TRAI gazette PDF (search summary, 2026-10-18) |
| Unsolicited Commercial Communication (UCC) | Commercial communication that the recipient has not consented to or that contravenes the recipient's registered preference. Exact clause text UNVERIFIED. | TRAI press material (search summary) |
| Promotional / Transactional / Service | Promotional = advertising or marketing content; Transactional = triggered by a transaction; Service = based on an existing business relationship to facilitate a consented transaction. 2025 amendment: content mixing promotional with any other type is treated as promotional. | Khaitan & Co summary of the Second Amendment (search summary, 2026-10-18) |
| Telemarketer | Reg. 2(bp): person or legal entity "engaged in the activity of transmission or delivery of commercial communication or scrubbing or aggregation" | legitquest.com copy of the regulation (search summary) |
| Registered Telemarketer (RTM) | Reg. 2(ay): "any telemarketer who is registered with the access provider(s) in accordance with the procedure and conditions specified in these regulations" | legitquest.com (search summary) |
| Sender / Principal Entity (PE) | Reg. 2(bf) "Sender": the individual, business or legal entity on whose behalf commercial communication is sent. A PE must register with an access provider on the DLT platform and may send directly or via an RTM. | TRAI consultation paper CP_28082024 (search summary) |
| Consent | Voluntary permission from a customer for a sender to send commercial communication about a specific purpose, product or service; "may be explicit or inferred as defined in these regulations". 2025 amendment: inferred consent valid only for the duration of the contractual relationship; explicit consent to complete a commercial transaction valid 7 days. | TRAI gazette 2018 and Khaitan summary (search summary) |
| Fully Blocked / preferences | "stoppage of all types of commercial communication requiring explicit consent except commercial communication sent under inferred consent". The 2026 amendment migrates FULLY BLOCK registrations to BLOCK PROMO. | search summary of Reg. text and TRAI 2026 consultation paper |

### 1.2 DLT framework, headers and number series

- Senders (PEs) and telemarketers register on an access provider's Distributed Ledger Technology (DLT) platform; headers, content templates and consent templates are registered there. Jio operates its own DLT portal; a PE that wants to originate traffic itself must also register as a Telemarketer and sign an agreement with RJIL (search summaries of the Jio DLT PE-TM manual and smscountry guide, 2026-10-18).
- Second Amendment (TRAI, 12 February 2025, Regulation_12022025.pdf; press release PR No. 11/2025; PIB PRID 2102413): senders may no longer use ordinary 10-digit numbers for telemarketing; "all commercial communications originate from designated headers or specific number series"; the 140 series remains for promotional calls and the new 1600 series is for transactional and service calls so the recipient can identify the call type from the CLI (PIB, search summary, 2026-10-18). Headers carry type suffixes (-P promotional, -S service, -T transactional, -G government) (secondary summaries; UNVERIFIED against the gazette text).
- Most provisions in force from 12 February 2025; complaint-mechanism provisions from 13 April 2025 (Khaitan, search summary).
- Third Amendment: draft published 13 March 2026, notified 18 September 2026 (TRAI PR No. 119/2026 listed in search results; text not retrievable). Secondary summaries report: complaint-based action can start at 3 unique complaints in 10 days when the number is also flagged by the access provider's AI/ML UCC_Detect system; entities using automated dialers / application-to-person voice must declare that use and their calling numbers to the access provider, and undeclared A2P calls are treated as UCC; a consumer appeal against complaint resolution is added (anantamias.com and barandbench.com, search summary, 2026-10-18; UNVERIFIED against the notified text).

### 1.3 Preferences (DND) and time bands

- Preference registration (NCPR, "DND") is per customer with content categories and time bands. Regulation 9 gates all commercial communication on the recipient's registered preference or consent (per a documented reading of the gazette in github.com/Bubblegunn/proactive-gate/pull/29, retrieved 2026-10-18).
- Schedule II item 3, Note 1: "Time Bands (i), (ii), (iii) and (ix) shall be default OFF for all customers", i.e. 00:00-06:00, 06:00-08:00, 08:00-10:00 and 21:00-24:00 are off unless the customer opts in, which makes 10:00-21:00 the net default window (same source). The widely quoted "9 AM to 9 PM" is a simplification. Jio's own Telecom Consumer Charter 2025 states no telemarketing is permitted 9:00 PM to 10:00 AM (search summary of myjiostatic.cdn.jio.com/jio/regulatory/rjil-telecom-charter-2025.pdf, 2026-10-18; PDF not retrievable).
- SELL AGENT's default quiet hours 21:00-09:00 are therefore slightly more permissive in the morning than the regulatory default (10:00). See gap table.

### 1.4 Enforcement against a consumer SIM used for promotion (Regulation 25 ladder)

TRAI directions of 2024 (Direction_25072024.pdf, Direction_13082024.pdf) restate the Regulation 25 ladder for Unregistered Telemarketers (UTMs), which includes any subscriber whose ordinary telecom resources generate UCC complaints (search summary, 2026-10-18):
1. First violation: warning from the Originating Access Provider.
2. Second: "the Sender shall be put under Usage Cap for a period of six months".
3. Third or later: "all telecom resources of the Sender shall be disconnected for a period up to two years" and the sender is blacklisted; blacklisting is shared with all access providers on DLT within 24 hours and they disconnect within a further 24 hours; no new resources may be allocated to the sender.

Secondary summaries of the 2025 amendment additionally report 15-day outgoing barring on a first valid violation and one-year disconnection plus blacklisting across all access providers on repeat (frejun.com, sigmachambers.in; UNVERIFIED against the gazette). Financial disincentives in the 2025 amendment fall on access providers for misreporting UCC counts: Rs 2 lakh, Rs 5 lakh, then Rs 10 lakh per instance (PIB, search summary). Complaint window extended to 7 days (Khaitan, search summary). Access providers must run AI/ML-based UCC_Detect systems (TRAI PR 51/2023 and 2026 direction, search summary). Scale: TRAI reported more than 18 lakh numbers disconnected and about 1,150 entities blacklisted after the 2025 amendments (medianama, search summary).

### 1.5 Obligation chain for SELL AGENT's intended setup

A promotional call placed by software through a consumer Jio SIM to a gym owner who has not consented is, under the definitions above, commercial communication from an unregistered sender on a 10-digit number. The chain is: Sender (FITRON / operator) -> must be a registered PE on DLT -> must route promotional voice through a registered telemarketer/CPaaS holding 140-series resources -> must scrub against NCPR preferences and hold registered consent -> must respect time bands and complaint handling. None of these links can be satisfied by the desktop application itself; they are commercial and registration acts of the operator.

## 2. Reliance Jio terms for consumer SIM use

- Jio Telecom Consumer Charter 2025: "Service shall not be used to make unauthorised and unsolicited telemarketing/commercial calls/SMS, other than where designated number series are being used for the purpose"; use in SIMBOX devices is prohibited; subscriber indemnifies RJIL for misuse; Jio will not send commercial communication to NCPR-registered numbers (search summary of the charter PDF, 2026-10-18; UNVERIFIED verbatim).
- Jio postpaid plan terms (Mobility-Postpaid-Plans.pdf, JioFiber, JioPlus): plans are for personal use only; Jio may discontinue free voice benefits in cases of misuse, fraudulent use, or unauthorised telemarketing and commercial use (search summary; UNVERIFIED verbatim).
- The general consumer terms page https://www.jio.com/terms-conditions could not be retrieved (DNS blocked) and no archived copy was reachable: UNVERIFIED.
- Consequence: UCC complaints against the SIM feed the Regulation 25 ladder (usage cap, disconnection up to two years, cross-operator blacklist). This applies to the SIM holder personally.

## 3. Digital Personal Data Protection Act 2023 and DPDP Rules 2025

Sources: Act No. 22 of 2023 (assent 11 August 2023; indiacode PDF listed in search results but not retrievable), DPDP Rules 2025 (gazette 13/14 November 2025 per differing secondary sources). All section references below come from search summaries of secondary sources (seclore.com, dpdpa.com, ksandk.com, EY, Hogan Lovells, Vision IAS; 2026-10-18) and are UNVERIFIED against the gazette text.

- Applicability (s.3): digital personal data processed in India, and outside India when offering goods or services to persons in India. "Personal data" is any data about an individual who is identifiable by or in relation to such data; a gym owner's name, personal mobile number and email are personal data even when collected in a business context. Business names alone are not.
- Grounds (s.4): consent (s.6) or "certain legitimate uses" (s.7). Notice (s.5): itemised description of personal data, purpose, how to exercise rights and complain to the Board; Rule 3 requires the notice to be understandable independently and in plain language.
- Consent (s.6): free, specific, informed, unconditional, unambiguous, for a specified purpose; withdrawable as easily as given (s.6(6) per secondary sources).
- Data fiduciary obligations (s.8): reasonable security safeguards (s.8(5), Rule 6: encryption, access control, logs retained at least one year); breach intimation to the Board and each affected data principal (s.8(6), Rule 7: without delay, full particulars within 72 hours); erasure when consent is withdrawn or purpose is served, whichever is earlier, including by processors (s.8(7), Rule 8; the Third Schedule's 3-year rule and 48-hour pre-erasure notice apply to large e-commerce, gaming and social-media platforms only).
- Rights (ss.11-14): access, correction and erasure (s.12), grievance redressal, nomination.
- Penalties (s.33 and Schedule): up to Rs 250 crore for failure of security safeguards; up to Rs 200 crore for breach-notification failures (secondary figures).
- Commencement: Data Protection Board and appeal provisions from 13 November 2025; Rule 4 (consent managers) at 12 months; Rules 3, 5-16, 22, 23 at 18 months, i.e. 13 May 2027 (sources differ by one day). Until then, IT Act s.43A and the SPDI Rules 2011 remain the operative data-protection law; s.44(2) of the DPDP Act omits s.43A on commencement (ksandk.com, Linklaters; search summary).
- Local-only deployment does not remove fiduciary duties: notice, consent records, purpose limitation, security of the SQLite file and backups, breach handling, erasure on request, and retention limits still apply. What it removes is cross-border transfer and most processor contracts.

## 4. IT Act 2000 / SPDI Rules 2011

Still in force until the DPDP substantive provisions commence (expected 13 May 2027). Relevant now: s.43A reasonable security practices (ISO/IEC 27001 or equivalent documented programme), Rule 4 privacy policy, Rule 5 consent for sensitive personal data (phone numbers alone are not SPDI, but passwords and financial data are), s.72A punishment for disclosure in breach of a lawful contract, s.69 (government interception only). Sources: search summaries (ksandk.com, slm.mba), 2026-10-18.

## 5. Call recording consent expectations

- There is no Indian statute requiring all-party consent for a participant to record their own call; secondary sources disagree on whether participant recording needs the other party's consent (iPleaders, bnblegal vs Wikipedia; search summary). Interception by a non-participant requires authorisation under Telegraph Act s.5(2). Courts have treated covert recording as an Article 21 privacy intrusion (PUCL v Union of India telephone-tapping case; Delhi High Court NSE/ISEC matter cited by ksandk.com; search summary, citation details UNVERIFIED).
- Under DPDP, a recording of an identifiable person's voice is personal data; it needs notice and a lawful ground, and must be erased when the purpose ends.
- Engineering consequence: `privacy.record_calls` defaults to false, the call row carries `recording_consent` and `recorded` flags, and `privacy.recording_disclosure_text` is played/read when assistance or recording is on. Recording stays off until the operator has a documented disclosure-and-consent practice.

## 6. GAP TABLE

| # | Requirement | SELL AGENT today (code reference) | Operator responsibility | Status |
|---|---|---|---|---|
| 1 | Sender registered as Principal Entity on DLT | Not applicable to software; campaign `authorized_by` field records who approved | Register FITRON/operator entity on an access-provider DLT portal | operator action |
| 2 | Promotional voice from 140-series via RTM/CPaaS, not a 10-digit consumer number | `telecom/manual.py` and `telecom/android.py` only dial via operator or paired phone; no 140 route exists | Contract a registered telemarketer or licensed CPaaS; add a route adapter later | blocked (no compliant route in product) |
| 3 | NCPR/DND preference scrubbing before each promotional call | Local suppression list with reason `dnd` (`services/suppression.py`) and `eligibility.check` step 3; no NCPR lookup | Scrub lists through the DLT scrubbing service of the telemarketer; import results as `dnd` suppressions | operator action |
| 4 | Consent record (explicit/inferred), expiry handling | `ContactPermission` rows (status, source, evidence, expires_at); `calling.require_consent` default true; campaigns `requires_consent` default true | Collect consent artefacts (forms, inbound enquiry logs) and register consent templates on DLT where required | implemented (local) / operator action (DLT) |
| 5 | Opt-out honoured immediately and permanently | `suppression.add` sets `opted_out`, `consent_status=withdrawn`; removal needs justification and is audited | Train staff to log verbal opt-outs during human-assisted calls | implemented |
| 6 | Time-band compliance | Quiet hours default 21:00-09:00 (`settings_service.DEFAULTS`), per-campaign override, enforced in `eligibility.check` step 6 | Set quiet hours to 21:00-10:00 to match the regulatory default window | implemented; unresolved question (default should probably move to 10:00) |
| 7 | Volume limits / anti-spam behaviour | 10/hour, 50/day, 60 s spacing, 3 attempts per contact, campaign daily cap (`eligibility.check` steps 7-8) | Keep limits; raise only with a registered route | implemented |
| 8 | Identity disclosure and automated-assistance disclosure | `calling.identity_disclosure_required` true; `privacy.recording_disclosure_text` | Script wording review | implemented |
| 9 | Auditability of every call decision | Eligibility result stored on `CallJob`; append-only `AuditEvent` with secret redaction (`services/audit.py`) | Retain audit exports for complaint handling (7-day complaint window, 2025 amendment) | implemented |
| 10 | Human-in-the-loop default; no autonomous robocalls | `calling.default_mode=human_assisted`; autonomous requires authorised campaign, settings flag and release gate (`release_gate.autonomous_calling_allowed`, read-only, false) | Do not enable autonomous mode on a consumer SIM; the 2026 amendment requires declaring auto-dialer use to the access provider | implemented (gate closed) |
| 11 | DPDP notice and purpose limitation | Contact `lead_source`, `source_url`, `source_verification`; no notice artefact generator | Publish privacy notice; record the purpose per campaign | operator action |
| 12 | Security safeguards (s.8(5), SPDI s.43A) | Localhost-only API, token auth, TLS for LAN pairing, AES-GCM encrypted backups with scrypt, secret store, audit log | Disk encryption on the Windows host, access control, incident runbook | implemented (partial) / operator action |
| 13 | Retention and erasure | Transcript retention 90 days, logs 30 days, retention job (`api/v1/settings.py: run_retention`); hard delete of contacts; backup rotation | Define retention policy; run erasure on data-principal request | implemented |
| 14 | Breach notification (72 h) | Audit log supports reconstruction; no breach workflow | Breach register and notification process | operator action |
| 15 | Call recording consent | Off by default; per-call consent flag | Decide whether to record at all; if yes, verbal consent script | implemented (off) |
| 16 | Jio acceptable use | Rate limits reduce complaint risk but do not make promotional use permitted | Do not run promotional campaigns from the consumer SIM | blocked |

## 7. Conclusion

An ordinary Jio consumer SIM is not an authorised channel for automated commercial promotional calling. Basis: TCCCPR 2018 requires senders and telemarketers to be registered, the February 2025 Second Amendment bars telemarketing from ordinary 10-digit numbers and reserves the 140 series for promotional and 1600 for transactional/service calls (PIB PRID 2102413, TRAI PR 11/2025; search summaries), Regulation 25 and the 2024 TRAI directions provide warning, six-month usage cap, disconnection up to two years and cross-operator blacklisting for unregistered senders, and Jio's Telecom Consumer Charter 2025 prohibits unsolicited telemarketing from its service except on designated number series. The September 2026 Third Amendment adds a declaration duty for automated dialers, which an undeclared desktop auto-dialer would breach.

Lawful alternatives:
1. Registered-telemarketer / CPaaS route: FITRON registers as a PE, promotional calls originate on 140-series numbers through a licensed provider with DLT scrubbing and consent templates; SELL AGENT would need a SIP/WebRTC route adapter (see docs/TELECOM_FEASIBILITY.md).
2. Consented transactional or service calls to existing customers (inferred consent during the contract) on a 1600-series route.
3. Human-assisted calls by an operator to inbound leads and existing customers with recorded consent, which is the only mode SELL AGENT ships enabled; the software supplies scripts, eligibility checks, suppression, audit and outcome logging while a person dials and speaks.

Unresolved questions for the operator's counsel: whether a one-to-one human-dialled call to a business number that has enquired about FITRON is "commercial communication" needing a 140 route when the person speaks live; whether the 2026 auto-dialer declaration applies to a semi-automated click-to-dial on a consumer SIM; the verbatim text of the Jio consumer terms.
