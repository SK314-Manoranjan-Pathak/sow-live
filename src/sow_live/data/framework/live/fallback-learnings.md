# Learnings (generic fallback)

> **Source: built-in fallback.** The ShellKode wiki could not be reached, so these are generic AWS scoping gotchas only, not ShellKode's own lessons. Run `sow-live learnings` once the wiki is signed in to replace this file with the wiki digest.

### [Region] Model and GPU availability differs by region
- What: Bedrock models, inference profiles (in-region, geographic, global) and GPU instance families differ per region, and newer ones reach regions such as ap-south-1 later.
- Action: Confirm the exact model version, inference profile and instance family in the target region before scoping. Flag residency conflicts early.

### [Region] Not every AWS service or feature is in every region
- What: Newer services and features roll out region by region.
- Action: Verify service and feature availability in the target region before scoping it.

### [Compliance] Data residency can rule out cross-region inference
- What: Regulated customers (for example BFSI under RBI in India) often require data, and sometimes inference, to stay in-country.
- Action: Ask about data classification and frameworks up front. State a "no cross-region data transfer or inference" assumption when confirmed.

### [Pricing] Public list pricing differs from EA or EDP rates
- What: Estimates use public on-demand pricing; the customer may have negotiated discounts.
- Action: State the pricing basis explicitly as an assumption.

### [Pricing] LLM token costs dominate and are usage-sensitive
- What: For chatbot and agent workloads, inference is usually the largest and most variable line item.
- Action: Capture request volume and average input/output tokens; state them as estimate assumptions.

### [Integration] On-prem systems need network connectivity work
- What: "REST API integration" with an on-prem system needs VPN, Direct Connect or allow-listing from AWS.
- Action: Ask where each API is hosted and how AWS reaches it; list connectivity as a pre-requisite.

### [Integration] SSO needs specific identity-provider details
- What: OIDC/SAML integration needs tenant ID, client ID/secret and redirect URIs.
- Action: List these as pre-requisites before the auth phase.

### [Scope] "Produces requests" vs "executes actions" boundary
- What: Customers may assume the system also performs the action, not just raises the request or ticket.
- Action: State explicitly whether execution is in scope.
