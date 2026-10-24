"""Headless stand-in for an ollmcp session (same method as helpdesk-rag/scripts/23_mcp_test.py): a chat model sees the
CAG tool schema, decides whether to call it, receives the result, and answers. Run from the project root:
    PYTHONPATH=src uv run python scripts/mcp_check.py
CHAT_MODEL must differ from CAG_MODEL (see docs/08)."""
import asyncio, json, os, time
import ollama
from fastmcp import Client

CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen3:8b-16k")
cfg = json.load(open("mcp.json"))
cfg["mcpServers"]["cag"]["env"]["CAG_MAX_DOCS"] = os.getenv("CAG_MAX_DOCS", "150")
SEARCH = ["Our VPN drops every hour, any past tickets?", "Outlook keeps asking me to sign in on my Mac",
          "Printer on floor 3 is offline again, seen before?"]
NONSEARCH = ["hi there", "what is 17 times 23?", "thanks, that's all"]

async def main():
    async with Client(cfg) as client:
        tools = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema}}
                 for t in await client.list_tools()]
        print("tools:", [t["function"]["name"] for t in tools])
        for q in SEARCH + NONSEARCH:
            t0 = time.time(); msgs = [{"role": "user", "content": q}]
            r = ollama.chat(model=CHAT_MODEL, messages=msgs, tools=tools, think=False)
            calls = r["message"].get("tool_calls") or []
            info = ""
            if calls:
                msgs.append(r["message"])
                for c in calls:
                    res = await client.call_tool(c["function"]["name"], dict(c["function"]["arguments"]))
                    data = res.data if res.data is not None else json.loads(res.content[0].text)
                    info = f" cited={data.get('cited_ids')} cache={data.get('cache')}"
                    msgs.append({"role": "tool", "tool_name": c["function"]["name"], "content": json.dumps(data)})
                r = ollama.chat(model=CHAT_MODEL, messages=msgs, tools=tools, think=False)
            print(f"\nQ: {q}\n  tool_called={bool(calls)}{info}  ({time.time()-t0:.1f}s)\n  A: {r['message']['content'][:220]!r}")

asyncio.run(main())
