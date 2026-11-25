Generate the SoW using the sow-generator skill (v2 orchestration) for the engagement in the current folder, starting from a **live-captured brief**.

`build/brief.md` was written by sow-live during the customer discovery call and is marked `<!-- source: sow-live -->`. The clarifying round already happened with the customer on the call, so:

1. Skip Step 0's overview request, skip PASS 1 (gap analysis), and skip Step 2 (the clarifying round). Do not ask me questions.
2. Read `build/brief.md`, the call transcript and the evidence file it links to, `build/learnings.md` (ShellKode wiki learnings digest), and the `sol/` folder for extra background.
3. Anything still `{{placeholder}}`, marked _inferred_, or listed under open items: state it as an explicit assumption in the SoW (sections 10 Assumptions and 11 Out of Scope). Never invent values. Never name other ShellKode customers.
4. Run PASS 2 (populate) respecting the dependency DAG, then assemble, generate the `.docx`, validate, and render the PDF preview, exactly as in the skill.
5. At the end, list for me: the output file path, the assumptions you made because of gaps, and any cross-section inconsistencies you found.
