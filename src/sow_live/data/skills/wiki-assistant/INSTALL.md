# Installing the `wiki-assistant` skill

Search and contribute to the ShellKode org knowledge wiki (Outline) from any MCP client. Use when the user asks whether ShellKode has done something before, what we learned on a topic, who worked on a customer or project, or wants to find a challenge/solution/pattern — and when the user wants to add or update a project, customer, or challenge page in the wiki from a source they point you at (a SoW, MoM, codebase, README, notes, or anything else). Teaches index-first search over the wiki and how to draft pages in the correct team template with the controlled vocabulary. Connects through Outline's MCP tools.

This is an Agent Skill (AgentSkills.io standard): a folder containing a `SKILL.md` that
your agent loads on demand when your request matches its description.

## 1. Install the skill folder

Unzip `wiki-assistant.zip` — you get a `wiki-assistant/` folder with `SKILL.md` at its root. Put that
folder in your client's skills directory:

- **Kiro:** `~/.kiro/skills/wiki-assistant/`
  Create the `~/.kiro/skills/` directory if it does not exist, then drop the `wiki-assistant/`
  folder inside it (drag-and-drop in your file manager is fine). Restart Kiro or start a
  new chat so it picks up the skill. Kiro does not have a marketplace install — placing
  the folder is the way.
- **Claude Code:** `~/.claude/skills/wiki-assistant/` (or project-level `.claude/skills/`).
- **OpenAI Codex:** `.agents/skills/wiki-assistant/`.
- **Others (OpenCode, etc.):** your client's skills path; the folder must contain
  `SKILL.md` at its root.

Verify in Kiro: type `/` in chat — `wiki-assistant` should appear as a slash command. You can run
it explicitly that way, or just ask naturally and Kiro activates it from the description.

## 2. Connect to the ShellKode wiki MCP server

The skill uses the wiki's MCP tools, so add this server to your MCP config
(`~/.kiro/settings/mcp.json` for Kiro):

```json
{
  "mcpServers": {
    "shellkode-wiki": {
      "url": "https://wiki.shellkode.ai/mcp",
      "oauthScopes": ["read", "write"]
    }
  }
}
```

On the first wiki tool call, Kiro opens a browser to authenticate you against the wiki
(Google SSO). You act as yourself, with your own Outline permissions.

### If the wiki MCP server shows an auth error
When the connection needs to (re)authenticate, Kiro may show a failing **Retry**. **Retry
does not fix an auth problem.** Instead: **right-click the `shellkode-wiki` server in the
MCP panel and choose "Reauthenticate"** (not Retry). That reopens the sign-in flow and
clears the error. You may also need to reauthenticate occasionally when the session
expires.

## 3. Use it

Ask naturally, e.g.:
- "Have we done anything with voice agents? What did we learn?"
- "Do we have experience migrating customers to Bedrock?"
- "Add this project to the wiki — here's the SoW/README: …" (it drafts a page for your
  review before publishing).
