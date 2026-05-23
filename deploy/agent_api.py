"""
agent_api.py — Drop-in FastAPI server for serving LLMs on EC2.

Deploy this on your EC2 instances to serve models via POST /chat.

Usage:
    source ~/llm-env/bin/activate
    pip install fastapi uvicorn torch transformers accelerate
    python3 ~/agent_api.py

The server will start on port 8080 and serve POST /chat.
"""

import os
import sys
import traceback

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer

# ── Configuration ───────────────────────────────────────────────────────
# Change MODEL_PATH to your model directory or Hugging Face model ID
MODEL_PATH = os.environ.get("MODEL_PATH", "meta-llama/Llama-3.2-1B-Instruct")
PORT = int(os.environ.get("PORT", "8080"))
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print(f"[agent_api] Loading model: {MODEL_PATH}")
print(f"[agent_api] Device: {DEVICE}")
print(f"[agent_api] Port: {PORT}")

# ── Load Model ──────────────────────────────────────────────────────────
try:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
        device_map="auto" if DEVICE == "cuda" else None,
        trust_remote_code=True,
    )
    if DEVICE == "cpu":
        model = model.to("cpu")
    model.eval()
    print(f"[agent_api] ✅ Model loaded successfully on {DEVICE}")
except Exception as e:
    print(f"[agent_api] ❌ Failed to load model: {e}")
    traceback.print_exc()
    sys.exit(1)

# ── FastAPI App ─────────────────────────────────────────────────────────
app = FastAPI(title="LLM Agent API")


class ChatRequest(BaseModel):
    message: str
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9


class ChatResponse(BaseModel):
    response: str
    tokens_used: int = 0


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "model": MODEL_PATH, "device": DEVICE}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Generate a response from the model."""
    try:
        # Build conversation using chat template if available
        if hasattr(tokenizer, "apply_chat_template"):
            messages = [{"role": "user", "content": req.message}]
            input_text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        else:
            input_text = f"User: {req.message}\nAssistant:"

        inputs = tokenizer(input_text, return_tensors="pt").to(model.device)
        input_len = inputs["input_ids"].shape[1]

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=min(req.max_tokens, 2048),
                do_sample=req.temperature > 0,
                temperature=max(req.temperature, 1e-4),
                top_p=req.top_p,
                pad_token_id=tokenizer.eos_token_id,
            )

        # Decode only the new tokens (skip the input)
        new_tokens = outputs[0][input_len:]
        response_text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        tokens_used = len(new_tokens)

        return ChatResponse(response=response_text, tokens_used=tokens_used)

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")


# ── Entrypoint ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
