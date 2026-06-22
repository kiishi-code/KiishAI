@app.post("/chat")
async def chat(request: ChatRequest):
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
            "Content-Type": "application/json"
        }
        payload = {
            "model": "openrouter/free", 
            "messages": messages,
            "stream": True
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
                                delta = data_json['choices'][0]['delta']
                                if 'content' in delta:
                                    yield f"data: {delta['content']}\n\n"
                            except Exception:
                                continue

    # FIX: Add headers instructing proxies (like Render's Nginx layer) not to buffer this data
    return StreamingResponse(
        stream_response(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no", # Strictly tells Nginx to bypass response buffering
            "Connection": "keep-alive"
        }
    )
