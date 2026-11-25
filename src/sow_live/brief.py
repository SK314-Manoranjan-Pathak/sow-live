"""Render the captured call into build/brief.md (the orchestrator's input),
plus a review file with evidence, and the follow-up email."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .session import Session

STATUS_NOTE = {
    "stated": "",
    "confirmed": "",
    "proposed": " _(proposed by ShellKode, customer did not object)_",
    "context": " _(from pre-call notes, not discussed on the call)_",
    "inferred": " _(inferred, confirm)_",
    "previous_call": " _(from an earlier call with this customer)_",
}


def _rel(s: Session, p: Path) -> str:
    try:
        return str(p.relative_to(Path(s.state["engagement_path"])))
    except (KeyError, ValueError):
        return str(p)


def render_brief(s: Session, admin: dict[str, str]) -> str:
    st = s.state
    fields = st["fields"]
    lines = [
        "# Engagement Brief",
        "> Single source of truth for all specialist agents. **Source: sow-live** (captured during the discovery call). "
        "The clarifying round already happened on the call: do not run Pass 1 or ask the SA questions. "
        "Unknown values stay as `{{placeholders}}`; anything marked _inferred_ or _from pre-call notes_ should be "
        "stated as an assumption in the SoW.",
        "",
        "<!-- source: sow-live -->",
        f"- Live session: `{_rel(s, s.path)}`",
        f"- Call transcript: `{_rel(s, s.path / 'transcript.md')}`",
        f"- Field evidence (quotes + timestamps): `{_rel(s, s.path / 'brief-review.md')}`",
        "- Team learnings (ShellKode wiki digest): `build/learnings.md`",
        f"- Call date: {st['started_at'][:10]}",
        "",
    ]
    section = None
    for f in s.catalog:
        if f["section"] != section:
            section = f["section"]
            lines += ["", f"## {section}"]
        fid = f["id"]
        if f["ask"] == "admin":
            val = admin.get(fid) or (fields.get(fid) or {}).get("value") or f"{{{{{fid}}}}}"
            lines.append(f"- {f['label']}: {val}")
            continue
        rec = fields.get(fid)
        if not rec:
            lines.append(f"- {f['label']}: {{{{{fid}}}}}")
            continue
        note = STATUS_NOTE.get(rec.get("status", ""), "")
        lines.append(f"- {f['label']}: {rec['value']}{note}")
        if rec.get("conflict"):
            lines.append(f"  - ⚠ conflicting statement: {rec['conflict']}")

    lines += ["", "## Call summary", st.get("summary") or "(none)"]

    org = [l for l in st["lookups"] if l["state"] == "done" and l["kind"] == "org_experience"]
    if org:
        lines += ["", "## ShellKode experience discussed on the call (from the org wiki)",
                  "> Internal context. Use it for reusable approaches, risks and timeline realism. "
                  "**Never name other ShellKode customers in the SoW.**"]
        for l in org:
            a = l.get("answer", {})
            lines.append(f"- **Q:** {l['query']}  ")
            lines.append(f"  **A:** {a.get('headline', '')} _(wiki: {a.get('confidence', '?')})_")
            if a.get("sow_impact"):
                lines.append(f"  - SoW impact: {a['sow_impact']}")
            for src in a.get("sources", [])[:3]:
                lines.append(f"  - Wiki page: [{src.get('title', src.get('url'))}]({src.get('url')})")

    answers = [l for l in st["lookups"] if l["state"] == "done" and l["kind"] != "org_experience"]
    if answers:
        lines += ["", "## AWS checks made during the call (advisor)"]
        for l in answers:
            a = l.get("answer", {})
            lines.append(f"- **Q:** {l['query']}  ")
            lines.append(f"  **A:** {a.get('headline', '')} _(confidence: {a.get('confidence', '?')})_")
            if a.get("sow_impact"):
                lines.append(f"  - SoW impact: {a['sow_impact']}")
            for src in a.get("sources", [])[:3]:
                lines.append(f"  - Source: [{src.get('title', src.get('url'))}]({src.get('url')})")

    lines += ["", "## Assumptions (not settled on the call; state these in the SoW)"]
    lines += [f"- {a}" for a in st.get("assumptions") or []] or ["- {{assumption_1}}"]

    lines += ["", "## Open items / flags (from learnings.md or unresolved)"]
    items = [f"- [{f.get('learning', 'flag')}] {f['text']}" for f in st["flags"]]
    items += [f"- {o}" for o in st.get("open_items") or []]
    lines += items or ["- none"]

    if st["notes"]:
        lines += ["", "## SA notes typed during the call"]
        lines += [f"- [{n['ts']}] {n['text']}" for n in st["notes"]]
    return "\n".join(lines) + "\n"


def render_review(s: Session) -> str:
    st = s.state
    out = [f"# Brief review: {st['client']} ({st['started_at'][:10]})",
           "Every captured field with the quote it came from. Fix anything wrong in `build/brief.md`.", ""]
    for f in s.catalog:
        if f["ask"] != "call":
            continue
        rec = st["fields"].get(f["id"])
        if not rec:
            mark = "❌" if f["tier"] == "critical" else "·"
            out.append(f"- {mark} **{f['label']}** ({f['tier']}): _not captured_")
            continue
        out.append(f"- ✅ **{f['label']}** [{rec.get('status')}]: {rec['value']}")
        if rec.get("evidence"):
            out.append(f"  - {rec['evidence']}")
        if rec.get("previous"):
            out.append(f"  - earlier value: {rec['previous']}")
    unanswered = [q for q in st["questions"] if q["state"] in ("open", "asked")]
    if unanswered:
        out += ["", "## Questions not answered on the call"]
        out += [f"- {q['text']}" for q in unanswered]
    return "\n".join(out) + "\n"


def write_outputs(s: Session, admin: dict[str, str], build_dir: Path) -> dict[str, Path]:
    build_dir.mkdir(parents=True, exist_ok=True)
    brief_path = build_dir / "brief.md"
    if brief_path.exists():
        backup = s.path / f"previous-brief-{date.today().isoformat()}.md"
        backup.write_text(brief_path.read_text())
    brief = render_brief(s, admin)
    brief_path.write_text(brief)
    (s.path / "brief.md").write_text(brief)
    review = s.path / "brief-review.md"
    review.write_text(render_review(s))
    paths = {"brief": brief_path, "review": review}
    if s.state.get("followup_email"):
        p = s.path / "followup-email.md"
        p.write_text(s.state["followup_email"].strip() + "\n")
        paths["email"] = p
    return paths
