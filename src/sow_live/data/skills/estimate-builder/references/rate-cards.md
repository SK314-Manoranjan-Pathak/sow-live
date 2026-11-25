# Rate cards & effort estimation guidance

> **Important:** This framework ships with **no hardcoded rates**. Rates are commercially sensitive and vary per engagement. Always obtain the current rate card from the user (or the account/commercial owner) before filling the Commercials table. Where a rate is unknown, leave the `{{cost}}` placeholder.

## Commercials table structure

| Resource | Duration (Weeks) | Total Cost INR |
| :---: | :---: | :---: |
| Solutions Architect | {{weeks}} | {{cost}} |
| Senior AI Engineer | {{weeks}} | {{cost}} |
| AI Engineer | {{weeks}} | {{cost}} |
| Project Manager | {{weeks}} | {{cost}} |

## Estimating effort (duration in weeks)

Distribute effort proportionally to each role's involvement across phases. Guidance:

- **Solutions Architect** — heavy at start (design, requirement confirmation) and at phase sign-offs; lighter mid-build.
- **Senior AI Engineer / Lead** — steady across build phases; owns agent orchestration and integration quality.
- **AI / Data Engineer** — peaks during build and integration phases.
- **Project Manager** — light-but-continuous across the whole timeline.

Total calendar duration for a typical multi-phase platform: **16–20 weeks**, with phases overlapping to enable parallel workstreams.

## Two cost dimensions — keep separate

1. **AWS infrastructure cost** — from the pricing MCPs, shown in section 9.1 with the calculator link. Monthly recurring.
2. **Professional services cost** — the Commercials table (9.2). One-time engagement cost by role.

Do not conflate the two. The SoW presents both.
