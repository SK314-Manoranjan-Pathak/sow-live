# Seed learnings to migrate into the ShellKode wiki

These entries came with the original SoW framework. `sow-live wiki-seed` drafts each one into the wiki for review (draft-only, never published).

## Region & Availability

### [Region] GPU capacity is constrained in Mumbai (ap-south-1)
- What: On-demand GPU instance families (e.g. P4/P5, some G5) have limited/variable availability in ap-south-1, and Bedrock model availability differs by region.
- Why it matters: A design assuming self-hosted GPU inference or a specific Bedrock model in Mumbai may not be deployable; can force a region change (data-residency conflict) or a model swap.
- Action: Confirm the exact models/instances are GA in the target region before committing. If data must stay in India and a model isn't available in ap-south-1, flag it early. Prefer Bedrock serverless models confirmed available in-region.
- Added by: seed example

### [Region] Not every AWS service/feature is in every region
- What: Newer services and features roll out to ap-south-1 later than us-east-1.
- Why it matters: Scope may reference a service unavailable in the client's required region.
- Action: Verify service + feature availability in the target region (use the awsknowledge MCP / regional availability) before scoping it.
- Added by: seed example

## Data Residency & Compliance

### [Compliance] Indian financial workloads often carry RBI data-localization needs
- What: BFSI clients in India frequently require data (and sometimes inference) to stay within India.
- Why it matters: Rules out cross-region inference, some managed services, and certain model endpoints.
- Action: Ask about data classification and applicable frameworks (RBI, etc.) up front. Add a "no cross-region data transfer/inference" assumption when confirmed.
- Added by: seed example

## Pricing & Estimates

### [Pricing] Public API pricing != enterprise/EA negotiated rates
- What: Estimates use public on-demand pricing; the client may have EA/committed-use discounts.
- Why it matters: Quoted infra cost may differ materially from the client's actual bill.
- Action: State the pricing basis explicitly as an assumption. Note EA-rate integration is out of scope unless requested.
- Added by: seed example

### [Pricing] LLM token costs dominate and are usage-sensitive
- What: For chatbot/agent workloads, model inference is usually the largest and most variable line item.
- Why it matters: Small changes in requests/day or tokens/request swing the monthly estimate a lot.
- Action: Capture expected request volume and average input/output tokens; state them as estimate assumptions.
- Added by: seed example

## Integrations

### [Integration] Confirm ITSM/API hosting (cloud vs on-prem) and connectivity early
- What: Systems like ManageEngine may be on-prem, requiring VPN/PrivateLink/allow-listing from AWS.
- Why it matters: Network connectivity work can add effort and dependencies not obvious from "REST API integration".
- Action: Ask where the API is hosted and how AWS will reach it; capture as a pre-requisite.
- Added by: seed example

### [Integration] Auth via ALB OIDC needs specific IdP details
- What: Azure AD OIDC via ALB needs tenant ID, client ID/secret, and redirect URIs.
- Why it matters: Missing IdP details block SSO setup and UAT.
- Action: List these as pre-requisites the client must provide before the auth phase.
- Added by: seed example

## Delivery & Scope

### [Scope] "Produces requests" vs "executes provisioning" is a common boundary confusion
- What: Clients may assume the system also provisions infra, not just generates the request/ticket.
- Why it matters: Scope creep and acceptance disputes.
- Action: State explicitly whether execution is in or out of scope. Default: system produces requests; client teams fulfill.
- Added by: seed example
