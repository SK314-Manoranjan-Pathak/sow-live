# Engagement Brief

> Single source of truth for all specialist agents. The orchestrator writes this after the clarifying round. Agents read it (never re-ask the user). Unknown values stay as `{{placeholders}}`.

## Client & commercial
- Client legal name: {{client_legal_name}}
- Client short name: {{client_short_name}}
- Registered office: {{client_address}}
- Effective date: {{effective_date}}
- Expiration date: {{expiration_date}}
- Author / preparer: {{author}}
- Rate card available? {{yes_no}} (rates: {{rate_card_or_placeholder}})

## Solution overview
- One-line objective: {{objective}}
- Problem today: {{current_state}}
- What we deliver: {{solution_summary}}
- Target users / volume: {{users_and_volume}}

## Region & data residency
- Target region(s): {{region}}
- Data residency / localization: {{residency_rules}}
- Cross-region inference/data allowed? {{yes_no}}
- Services/models confirmed GA in region? {{notes}}   ← check `build/learnings.md` (e.g. GPU in ap-south-1)

## Identity & auth
- Mechanism: {{auth}}
- IdP details available (tenant/client/redirect)? {{notes}}

## Integrations & APIs
- Systems: {{systems}}
- Hosting (cloud/on-prem) + connectivity: {{hosting_connectivity}}
- API docs/creds/test env available? {{notes}}

## Scale / availability / AI params
- Users, RPS/volume: {{scale}}
- Availability tier, RTO/RPO: {{availability}}
- AI: avg input/output tokens, images/request: {{ai_params}}

## Cost & pricing basis
- Pricing basis: {{public_or_ea}}
- Budget / tier: {{budget}}
- Include RI/SP/CUD? {{yes_no}}

## Models / AI specifics
- Model(s): {{models}}  (region-available? {{notes}})
- Managed (Bedrock serverless) vs self-hosted: {{choice}}
- Fine-tuning in scope? {{yes_no}}

## Scope & phasing
- Phases: {{phases}}
- Must-have vs optional: {{priorities}}
- Delivery boundaries (executes vs produces requests, channels, languages): {{boundaries}}

## Architecture components (for diagram-agent)
- Key components / services: {{components}}

## Confirmed assumptions
- {{assumption_1}}
- {{assumption_2}}

## Open items / flags (from `build/learnings.md` or unresolved)
- {{flag_1}}
