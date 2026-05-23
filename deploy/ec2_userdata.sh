#!/bin/bash
# ============================================================
#  Playground EC2 Model Server — Auto-Bootstrap (User Data)
# ============================================================
#
#  Paste this entire script into the "User data" field when
#  launching any EC2 instance. It will:
#    1. Install Python + dependencies
#    2. Authenticate with Hugging Face
#    3. Write agent_api.py
#    4. Create a systemd service that auto-starts on boot
#    5. Start serving POST /chat on port 8080
#
#  EDIT ONLY THESE TWO LINES BEFORE PASTING:
# ============================================================

MODEL_PATH="meta-llama/Llama-3.1-8B-Instruct"
HF_TOKEN="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"

# ============================================================
#  Do not edit below unless you know what you're doing.
# ============================================================

PORT=8080
INSTALL_DIR="/home/ubuntu/playground-model"
VENV="$INSTALL_DIR/venv"
LOG="/var/log/playground-model-setup.log"

exec > >(tee -a "$LOG") 2>&1
echo "=== Playground model setup started at $(date) ==="
echo "=== Model: $MODEL_PATH ==="

# ── 1. System packages ────────────────────────────────────
apt-get update -y
apt-get install -y python3.11 python3.11-venv python3-pip git curl

# ── 2. Install dir + venv ────────────────────────────────
mkdir -p "$INSTALL_DIR"
python3.11 -m venv "$VENV"
source "$VENV/bin/activate"
pip install --upgrade pip --quiet

# ── 3. Python deps ───────────────────────────────────────
# Detect GPU
if python3 -c "import subprocess; r=subprocess.run(['nvidia-smi'],capture_output=True); exit(0 if r.returncode==0 else 1)" 2>/dev/null; then
    echo "=== GPU detected — installing CUDA torch ==="
    pip install torch --index-url https://download.pytorch.org/whl/cu118 --quiet
else
    echo "=== No GPU — installing CPU torch ==="
    pip install torch --quiet
fi

pip install fastapi "uvicorn[standard]" transformers accelerate pydantic huggingface_hub --quiet

# ── 4. HF auth ───────────────────────────────────────────
echo "=== Authenticating with Hugging Face ==="
"$VENV/bin/python" -c "
from huggingface_hub import login
login(token='$HF_TOKEN', add_to_git_credential=False)
print('HF login OK')
"

# ── 5. Write agent_api.py ────────────────────────────────
cat > "$INSTALL_DIR/agent_api.py" << 'PYEOF'
"""
agent_api.py — Drop-in FastAPI server for serving LLMs on EC2.
Serves POST /chat and GET /health on port 8080.
"""

import os
import sys
import traceback

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_PATH = os.environ.get("MODEL_PATH", "meta-llama/Llama-3.2-1B-Instruct")
PORT = int(os.environ.get("PORT", "8080"))
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print(f"[agent_api] Loading model: {MODEL_PATH}")
print(f"[agent_api] Device: {DEVICE}")
print(f"[agent_api] Port: {PORT}")

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
    print(f"[agent_api] Model loaded successfully on {DEVICE}")
except Exception as e:
    print(f"[agent_api] Failed to load model: {e}")
    traceback.print_exc()
    sys.exit(1)

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
    return {"status": "ok", "model": MODEL_PATH, "device": DEVICE}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
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

        new_tokens = outputs[0][input_len:]
        response_text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        return ChatResponse(response=response_text, tokens_used=len(new_tokens))

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
PYEOF

# ── 6. Write .env file ───────────────────────────────────
cat > "$INSTALL_DIR/model.env" << EOF
MODEL_PATH=$MODEL_PATH
HF_TOKEN=$HF_TOKEN
PORT=$PORT
EOF

# ── 7. systemd service ───────────────────────────────────
cat > /etc/systemd/system/playground-model.service << EOF
[Unit]
Description=Playground LLM Model Server ($MODEL_PATH)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/model.env
ExecStart=$VENV/bin/python $INSTALL_DIR/agent_api.py
Restart=always
RestartSec=15
StandardOutput=journal
StandardError=journal
SyslogIdentifier=playground-model

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable playground-model
systemctl start playground-model

echo "=== Setup complete at $(date) ==="
echo "=== Model server will be available at http://\$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):$PORT/health ==="
echo "=== This may take 10-20 minutes while the model downloads. ==="
echo "=== Check progress: journalctl -u playground-model -f ==="
