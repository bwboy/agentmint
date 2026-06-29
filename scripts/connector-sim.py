#!/usr/bin/env python3
"""
AgentMint Connector Simulator

Simulates a real OpenClaw / Hermes connector for development. Connects to the
platform WS, replies to pings, and answers any question with a mock payload.

Usage:
    PLATFORM_URL=ws://localhost:8000/ws \
    CONNECTOR_ID=conn_xxxxxxxx \
    CONNECTOR_TOKEN=conn_sk_... \
    python scripts/connector-sim.py

Or pass via flags:
    python scripts/connector-sim.py --connector-id conn_xxx --token conn_sk_...
"""
import argparse
import asyncio
import json
import os
import random
import time

import websockets


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AgentMint Connector Simulator")
    p.add_argument("--url", default=os.getenv("PLATFORM_URL", "ws://localhost:8000/ws"))
    p.add_argument("--connector-id", default=os.getenv("CONNECTOR_ID"))
    p.add_argument("--token", default=os.getenv("CONNECTOR_TOKEN"))
    p.add_argument("--agent-type", default=os.getenv("AGENT_TYPE", "openclaw"))
    p.add_argument("--think-min", type=float, default=2.0)
    p.add_argument("--think-max", type=float, default=4.0)
    args = p.parse_args()

    if not args.connector_id or not args.token:
        p.error("--connector-id and --token (or env CONNECTOR_ID/CONNECTOR_TOKEN) are required")
    return args


def mock_answer(question: dict) -> dict:
    title = question.get("title", "")
    tags = ", ".join(question.get("tags", []))
    text = (
        f"## 关于 \"{title}\" 的回答\n\n"
        f"这是一个由 connector-sim 生成的模拟回答。\n\n"
        f"### 分析\n\n"
        f"根据标签（{tags}），我进行了如下分析：\n\n"
        f"1. 核心要点……\n"
        f"2. 关键考虑……\n"
        f"3. 建议方案……\n\n"
        f"```rust\nfn main() {{\n    println!(\"Hello\");\n}}\n```\n\n"
        f"> 此回答用于平台联调，不代表真实 Agent 输出。"
    )
    prompt_tokens = 600 + random.randint(0, 500)
    completion_tokens = 400 + random.randint(0, 600)
    return {
        "type": "answer",
        "request_id": question["request_id"],
        "status": "success",
        "content": {"text": text, "attachments": []},
        "model": "claude-opus-4-7",
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "capability": {
            "engine": {"provider": "anthropic", "model": "claude-opus-4-7"},
            "skills": [{"name": "rust-expert", "version": "2.1.0", "source": "community"}],
            "tools": [{"name": "web_search", "used": True}],
            "mcp_servers": [{"name": "github", "tools_exposed": 12}],
        },
        "duration_ms": 2500 + random.randint(0, 3000),
    }


async def handle_question(ws, question: dict, think_min: float, think_max: float):
    print(f"[sim] question: {question.get('title')} (req={question['request_id']})")
    await ws.send(json.dumps({"type": "ack", "request_id": question["request_id"]}))
    think = random.uniform(think_min, think_max)
    print(f"[sim]   thinking for {think:.1f}s ...")
    await asyncio.sleep(think)
    answer = mock_answer(question)
    await ws.send(json.dumps(answer, ensure_ascii=False))
    print(f"[sim]   answered ({answer['usage']['total_tokens']} tokens)")


async def run(args: argparse.Namespace):
    print(f"[sim] connecting to {args.url} …")
    async with websockets.connect(args.url) as ws:
        await ws.send(json.dumps({
            "type": "auth",
            "connector_id": args.connector_id,
            "token": args.token,
            "version": "1.0.0",
            "agent_type": args.agent_type,
            "agent_version": "0.1.0",
            "capabilities": ["chat"],
        }))

        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            t = msg.get("type")
            if t == "auth_ok":
                print(f"[sim] authenticated as \"{msg.get('connector_name')}\", "
                      f"heartbeat={msg.get('heartbeat_interval_ms')}ms")
            elif t == "auth_fail":
                print(f"[sim] auth failed: {msg.get('reason')}")
                return
            elif t == "ping":
                await ws.send(json.dumps({
                    "type": "pong",
                    "ts": int(time.time() * 1000),
                    "status": "idle",
                    "quota": {"used": 0, "max": 50, "remaining_auto": 40, "remaining_review": 10},
                }))
            elif t == "question":
                asyncio.create_task(handle_question(ws, msg, args.think_min, args.think_max))
            elif t == "update_config":
                await ws.send(json.dumps({"type": "config_ack",
                                          "applied_fields": list((msg.get("fields") or {}).keys())}))
            else:
                print(f"[sim] unknown msg: {t}")


async def main_with_reconnect():
    args = parse_args()
    backoffs = [0, 2, 4, 8, 30]
    attempt = 0
    while True:
        try:
            await run(args)
            print("[sim] connection closed cleanly")
            attempt = 0
        except Exception as e:
            print(f"[sim] connection error: {e}")
        # Exponential backoff, cap at 30s
        delay = backoffs[min(attempt, len(backoffs) - 1)]
        attempt += 1
        print(f"[sim] reconnecting in {delay}s (attempt {attempt})")
        await asyncio.sleep(delay)


if __name__ == "__main__":
    try:
        asyncio.run(main_with_reconnect())
    except KeyboardInterrupt:
        print("\n[sim] bye")
