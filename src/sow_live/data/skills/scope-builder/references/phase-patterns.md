# Reusable phase archetypes

Starting points for structuring scope. Adapt names and tasks to the actual project.

## Archetype A — Platform build (most common)

**Phase A: Core Platform & Foundational Setup**
- Requirement confirmation and design finalization
- AWS environment setup (compute, storage, IAM, networking, observability)
- Authentication & SSO
- Core application/interface development
- Primary integration(s)
- Testing & UAT

**Phase B: Intelligence / Value-Add Capabilities**
- Recommendation/analysis agents
- Cost/pricing integration
- Multimodal or advanced processing
- Consolidated output flow
- Testing & UAT

**Phase C: Extended Flows & Enhancements**
- Enhanced classification/routing
- Returning-user / delta flows
- Enquiry / informational capabilities
- Testing & UAT

**Phase D: Advanced Features (Optional)**
- IaC generation
- Cost-optimization recommendations
- Compliance checks
- Approval workflows
- Testing & UAT

## Archetype B — Data / Analytics platform

**Phase 1: Foundation** — data lake (S3 zones), catalog (Glue), query (Athena), IAM, networking
**Phase 2: Ingestion** — batch/streaming pipelines, transformation, quality checks
**Phase 3: Consumption** — warehouse/marts, BI connectivity, semantic layer
**Phase 4: Governance (Optional)** — lineage, access controls, cataloging, cost controls

## Archetype C — Migration / modernization

**Phase 1: Assess & Plan** — discovery, dependency mapping, wave planning
**Phase 2: Migrate** — rehost/replatform/refactor per wave
**Phase 3: Optimize** — right-sizing, cost optimization, observability
**Phase 4: Operate (Optional)** — runbooks, DR, handover

## Standard closing sub-section for every phase

Always end each phase with a **Testing & UAT** capability:
- Test all flows/integrations/logic delivered in the phase
- Conduct UAT with nominated users
- Collect feedback and apply refinements
