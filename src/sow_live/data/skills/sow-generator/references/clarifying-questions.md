# Clarifying questions — intake checklist

The SoW generator must **start from a solution overview provided by the user**, then ask only the questions still unanswered. Cross-check every answer against `build/learnings.md` (the wiki learnings digest) and raise any gotcha that applies (e.g. GPU/model availability in the target region).

## How to run the interview

1. Ask the user for a short **solution overview** (what they're building, for whom).
2. From that overview, **pre-fill** as many fields below as you can and read any existing workspace docs (briefs, design notes, prior SoWs).
3. Ask the **remaining** questions, grouped, in one or two concise rounds — don't interrogate one-by-one.
4. Before finalizing, replay a short summary of captured decisions and assumptions for confirmation.
5. Anything still unknown becomes a `{{placeholder}}` or an explicit assumption — never invented.

## Question bank (ask what's missing)

### A. Client & commercial
- Client legal name, short name, and registered office address?
- Effective and expiration dates for the agreement?
- Author/preparer name?
- Is there a rate card for the Commercials table, or should rates stay as placeholders?

### B. Solution scope & phasing
- What are the core capabilities in scope? Any explicit non-goals?
- Should the work be phased? If so, how (or use a standard archetype)?
- Which capabilities are "must-have" vs "optional/advanced"?

### C. Region & data residency  ⚠️ (see `build/learnings.md`)
- Target cloud region(s)? (e.g. ap-south-1 Mumbai)
- Any data-residency or localization requirements (RBI, GDPR, internal policy)?
- Is cross-region inference/data transfer allowed, or must everything stay in-region?
- Are the required services/models confirmed GA in the target region? (Flag GPU/model availability gaps.)

### D. Identity & authentication
- Auth mechanism? (e.g. Azure AD OIDC, Cognito, custom)
- If SSO via ALB/IdP: are tenant ID, client ID/secret, and redirect URIs available?
- Any role/permission requirements in scope?

### E. Integrations & APIs
- Which external systems must integrate? (ITSM, CRM, billing, etc.)
- For each: is it cloud-hosted or on-prem? How will AWS reach it (public, VPN, PrivateLink, allow-list)?
- Are API docs, endpoints, auth details, and a test environment available?
- Who owns/maintains those APIs during the engagement?

### F. Scale, availability & performance
- Expected users and request/transaction volume (peak + average)?
- Availability tier, RTO/RPO if applicable?
- For AI workloads: average input/output tokens per request, images per request?

### G. Cost & pricing basis
- Is public on-demand pricing acceptable, or are EA/negotiated rates in play?
- Target budget or budget tier, if any?
- Should the estimate include RI/SP/CUD options?

### H. Models / AI specifics (if applicable)
- Which model(s)? Confirmed available in the target region?
- Managed (Bedrock serverless) vs self-hosted? (Check GPU availability — see `build/learnings.md`.)
- Fine-tuning/training in scope, or prompt-engineering/RAG only?

### I. Delivery boundaries & assumptions
- Does the system execute actions, or only produce requests/artifacts?
- Channels in scope (web only? Teams/Slack/mobile?) and languages?
- UAT process, pilot group, and sign-off SLA?
- What testing is included (functional only, or load/security/pen-testing)?

### J. Architecture diagram
- Should the SoW include an architecture diagram? (Default: yes.)
- Provide/confirm the key components so the diagram skill can generate an accurate AWS diagram.

## Output of the interview

A confirmed inputs set that feeds `scope-builder`, `estimate-builder`, the diagram skill, and `docx-formatter`, plus a list of assumptions and any open items flagged from `build/learnings.md` (wiki learnings digest).
