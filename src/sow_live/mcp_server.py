"""`sow-live mcp`: a stdio MCP server over the personal knowledge graph.

Registered in each engagement's .kiro/settings/mcp.json as `sow-knowledge`, so
Kiro IDE/CLI can ask things like "what did FinServe say about volumes?" or
"have I already checked Claude availability in Mumbai?". Read-only.
"""

from __future__ import annotations

import json
import sys

from . import __version__, knowledge

TOOLS = [
    {
        "name": "list_engagements",
        "description": "List your engagements in the personal knowledge graph with call counts and last call date.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_engagement",
        "description": "Everything captured for one engagement across its discovery calls: brief fields with "
                       "evidence quotes, open questions, flags, call summaries and linked entities.",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string", "description": "client name or slug"}},
                        "required": ["name"]},
    },
    {
        "name": "search_knowledge",
        "description": "Search your knowledge graph (verified answers, captured facts, entities such as systems, "
                       "AWS services and constraints) across all your engagements.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"},
                                                         "limit": {"type": "integer", "default": 10}},
                        "required": ["query"]},
    },
    {
        "name": "find_verified_answers",
        "description": "Find AWS-documentation or ShellKode-wiki answers verified on earlier calls, with sources "
                       "and how many days ago they were checked. Re-check anything older than 30 days.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
]


def _call(name: str, args: dict):
    if name == "list_engagements":
        return knowledge.list_engagements()
    if name == "get_engagement":
        return knowledge.get_engagement(args.get("name", "")) or {"error": "no such engagement"}
    if name == "search_knowledge":
        return knowledge.search(args.get("query", ""), int(args.get("limit", 10)))
    if name == "find_verified_answers":
        return knowledge.known_answers(args.get("query", ""), limit=8)
    raise KeyError(name)


def _reply(msg_id, result=None, error=None) -> None:
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error:
        out["error"] = error
    else:
        out["result"] = result
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def serve() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, msg_id = msg.get("method"), msg.get("id")
        if msg_id is None:
            continue  # notification
        if method == "initialize":
            requested = (msg.get("params") or {}).get("protocolVersion") or "2025-06-18"
            _reply(msg_id, {"protocolVersion": requested, "capabilities": {"tools": {}},
                            "serverInfo": {"name": "sow-knowledge", "version": __version__}})
        elif method == "ping":
            _reply(msg_id, {})
        elif method == "tools/list":
            _reply(msg_id, {"tools": TOOLS})
        elif method == "tools/call":
            p = msg.get("params") or {}
            try:
                data = _call(p.get("name"), p.get("arguments") or {})
                _reply(msg_id, {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=1)}]})
            except KeyError:
                _reply(msg_id, error={"code": -32602, "message": f"unknown tool {p.get('name')}"})
            except Exception as e:
                _reply(msg_id, {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True})
        else:
            _reply(msg_id, error={"code": -32601, "message": f"method not found: {method}"})
    return 0
