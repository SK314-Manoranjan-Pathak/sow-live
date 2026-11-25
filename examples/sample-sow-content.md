# Worked example: brief → SoW

This shows how a short project brief flows through the framework into the content-JSON that the docx engine consumes. See `sample-content.json` for a runnable payload.

## 1. The brief a user might give

> "Create a SoW for Acme Manufacturing (Acme Manufacturing Private Limited, Pune) for a serverless data lake platform on AWS. Two phases — foundation then ingestion. Team: 1 SA for 4 weeks, 1 senior data engineer for 8 weeks. Target region ap-south-1. I'll fill in dates and rates."

## 2. What the orchestrator does

1. **sow-generator** confirms the gaps (effective/expiration dates, rate card → left as `{{placeholders}}`).
2. **scope-builder** expands the two phases into capabilities and task bullets (Archetype B — Data/Analytics), and builds the RACI + timelines tables. It checks service choices (S3, Glue, Athena) with `awsknowledge`.
3. **aws-architecture-diagram** skill produces `build/architecture.png`.
4. **estimate-builder** pulls S3/Glue/Athena pricing from `awspricing`, generates a `calculator.aws` link via `aws-calculator`, and builds the Commercials table (rates as `{{cost}}`).
5. **docx-formatter** assembles the payload and runs the engine.

## 3. Resulting file

```bash
python scripts/generate_sow_docx.py build/content.json "Acme Manufacturing - Serverless Data Lake Platform.docx"
```

## 4. Key mapping rules

| Brief element | Content-JSON |
|---|---|
| Client name/address | `cover.client_name` + Service Agreement `{{tokens}}` |
| Each phase | `h2` + objective `p` |
| Each capability | `h3` + `bullets` |
| Who does what | Roles `table` with R/A/C/I and `group` rows |
| Weeks per role | Commercials `table` |
| AWS monthly cost | Effort Estimate `p` with calculator link |

Anything the user did not supply becomes a `{{placeholder}}` — never invented.
