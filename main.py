import os
import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx
from typing import List, Dict, Any

# ====================== CONFIG ======================
# ⚠️ SECURITY: Do NOT hardcode API keys in production!
# Use environment variables instead:
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")

app = FastAPI(title="KiishiAI")

# Serve static files (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")


class ChatRequest(BaseModel):
    message: str
    history: List[Dict[str, Any]] = []
    user_name: str = "User"


@app.get("/", response_class=HTMLResponse)
async def home():
    """Serve the chat UI"""
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>Error: static/index.html not found</h1>", status_code=404)


@app.post("/chat")
async def chat(request: ChatRequest):
    # System prompt with personalization
    system_prompt = f"""
    You are KiishiAI, a friendly, intelligent, and helpful AI assistant.
    The user you are chatting with is named {request.user_name}.
    You MUST naturally address them by name '{request.user_name}' throughout the conversation when appropriate.
    Keep responses concise but informative and engaging.
    """

    messages = [{"role": "system", "content": system_prompt}]

    # Process history
    for msg in request.history:
        role = "assistant" if msg.get("role") in ["model", "assistant"] else "user"
        
        # Handle both formats: {content: "..."} and {parts: [{"text": "..."}]}
        text = ""
        if isinstance(msg.get("parts"), list) and len(msg["parts"]) > 0:
            text = msg["parts"][0].get("text", "")
        else:
            text = msg.get("content", "")

        if text.strip():
            messages.append({"role": role, "content": text})

    # Add current message
    messages.append({"role": "user", "content": request.message})

    async def stream_response():
        url = "https://openrouter.ai/api/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://yourdomain.com",  # Change to your actual domain
            "X-Title": "KiishiAI",
        }

        payload = {
            "model": "openrouter/free",   # or specify a concrete model
            "messages": messages,
            "stream": True,
            "temperature": 0.7,
            "max_tokens": 2048,
        }

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        error_text = await response.text()
                        yield f"data: {json.dumps({'error': f'API Error: {response.status_code}'})}\n\n"
                        return

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or line == "data: [DONE]":
                            continue
                        
                        if line.startswith("data: "):
                            data_str = line[6:]
                            try:
                                data_json = json.loads(data_str)
                                delta = data_json.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content")
                                if content:
                                    yield f"data: {content}\n\n"
                            except json.JSONDecodeError:
                                continue
                            except Exception:
                                continue
        except httpx.TimeoutException:
            yield 'data: {"error": "Request timed out"}\n\n'
        except Exception as e:
            yield f'data: {{"error": "Internal streaming error: {str(e)}"}}\n\n'

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )
