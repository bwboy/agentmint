#!/usr/bin/env python3
"""Mock OpenAI-compatible server for connector end-to-end testing.

Pretends to be the local Agent. Listens on the OpenClaw default port (18789)
and answers /v1/chat/completions with a canned response. Lets us verify the
connector's full path (WS → ack → HTTP → answer upload) without spending real
LLM credits.

Run:
    .venv/bin/uvicorn scripts.mock-openai-server:app --port 18789
"""
import time
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock OpenAI-compatible Agent")


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    temperature: float = 0.4


@app.post("/v1/chat/completions")
async def chat(req: ChatRequest):
    # Extract the actual user question from prompt
    user_msg = next((m for m in req.messages if m.role == "user"), None)
    user_text = user_msg.content if user_msg else ""
    title = ""
    for line in user_text.splitlines():
        if line.startswith("# 问题"):
            continue
        if line.strip():
            title = line.strip()
            break

    # Mimic some latency
    time.sleep(0.5)

    response_text = (
        f"## 关于「{title}」的回答\n\n"
        f"这是 mock-openai-server 生成的回答（用于联调验证）。\n\n"
        f"### 分析\n\n"
        f"1. **核心要点**：基于您的问题，我进行了以下推理\n"
        f"2. **关键考虑**：实际生产中应当评估方案的可行性\n"
        f"3. **建议**：从工程角度，推荐采用方案 X\n\n"
        f"### 示例代码\n\n"
        f"```rust\nfn main() {{\n    println!(\"OK\");\n}}\n```\n\n"
        f"> 这是 mock 服务，证明 Connector 的 HTTP 路径正常。换成真实 LLM 后回答会有质的区别。"
    )

    return {
        "id": f"mock-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": len(user_text) // 2,
            "completion_tokens": len(response_text) // 2,
            "total_tokens": (len(user_text) + len(response_text)) // 2,
        },
    }


@app.get("/")
async def root():
    return {"service": "mock-openai-server", "endpoint": "POST /v1/chat/completions"}
