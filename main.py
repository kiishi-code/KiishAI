import os
import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx

# 1. Try to read from Render dashboard first. 
# 2. If Render is buggy, it falls back to the secure string string directly!
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")

app = FastAPI(title="KiishiAI")

# Serve UI static assets
app.mount("/static", StaticFiles(directory="static"), name="static")

class ChatRequest(BaseModel):
    message: str
    history: list = []
    user_name: str = "User"

@app.get("/", response_class=HTMLResponse)
async def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/chat")
async def chat(request: ChatRequest):
    # System instructions
    personalized_prompt = f"""
    You are KiishiAI, a friendly, intelligent, and helpful AI assistant.
    The user you are chatting with is named {request.user_name}. 
    You MUST prioritize addressing them directly or casually acknowledging them by their name '{request.user_name}' naturally throughout the conversation.
    Keep responses concise but informative.
    """
    
    messages = [{"role": "system", "content": personalized_prompt}]
    
    for msg in request.history:
        role = "assistant" if msg.get("role") == "model" else msg.get("role", "user")
        text = ""
        if "parts" in msg and len(msg["parts"]) > 0:
            text = msg["parts"][0].get("text", "")
        else:
            text = msg.get("content", "")
            
        if text:
            messages.append({"role": role, "content": text})
        
    messages.append({"role": "user", "content": request.message})
    
    async def stream_response():
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://render.com", 
            "X-Title": "KiishiAI"
        }
        payload = {
            "model": "openrouter/free", 
            "messages": messages,
            "stream": True,
            "temperature": 0.7
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                async for line in response.aiter_lines():
                    if line:
                        line = line.strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data_json = json.loads(data_str)
                                if 'choices' in data_json and len(data_json['choices']) > 0:
                                    delta = data_json['choices'][0].get('delta', {})
                                    if 'content' in delta:
                                        yield f"data: {delta['content']}\n\n"
                            except Exception:
                                continue

    return StreamingResponse(
        stream_response(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )
