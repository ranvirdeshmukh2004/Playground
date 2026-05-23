# 🚀 Private Model Playground

A self-hosted LLM chat playground — inspired by [Groq Console](https://console.groq.com/playground) — for chatting with your own open-source models running on AWS EC2 instances.

**No API keys. No third-party services. Everything runs on your infrastructure.**

![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## ✨ Features

- 🎨 **Groq-style dark UI** — model dropdown, code panel, timer
- 🔄 **Real-time streaming** via Server-Sent Events (SSE)
- 📋 **Curl command panel** — auto-generated curl for each model
- ⏱️ **Response timer** — shows inference duration per query
- 📊 **Full logging** — every request logged with timestamps
- 🔌 **OpenAI-compatible** `/v1/chat/completions` proxy endpoint
- ➕ **Add models at runtime** — no restart needed
- 📱 **Responsive layout** — sidebar, chat, code panel all resize
- 🔒 **Private** — no data leaves your AWS account

---

## 📁 Project Structure

```
Playground/
├── main.py                   # FastAPI backend (API routes + SSE streaming)
├── config.py                 # Model registry (EC2 IPs + endpoints)
├── requirements.txt          # Python dependencies
├── static/
│   ├── css/styles.css        # Groq-style dark theme
│   └── js/app.js             # Frontend logic (chat, curl panel, timer)
├── templates/
│   └── index.html            # HTML template (Tailwind CSS)
├── deploy/
│   ├── agent_api.py          # Model server script (runs on each EC2)
│   ├── nginx.conf            # Nginx reverse proxy config
│   ├── supervisor.conf       # Supervisor process manager config
│   └── setup.sh              # EC2 setup script for the Playground server
└── logs/                     # Auto-generated request logs (gitignored)
```

---

## 🏗 Architecture

```
┌─────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│   Browser   │────▶│  EC2: Playground      │────▶│  EC2: Llama 3.2 1B  │
│  (User)     │     │  Nginx → Uvicorn      │────▶│  EC2: Qwen 0.5B     │
│             │◀────│  FastAPI (main.py)     │────▶│  EC2: Gemma 2 2B    │
└─────────────┘     └──────────────────────┘────▶│  EC2: Phi-4 Mini    │
                                                  └─────────────────────┘
```

Each model runs on its own EC2 instance with a FastAPI inference server (`deploy/agent_api.py`). The Playground backend proxies requests and streams responses.

---

## 🚀 Quick Start (Local)

### 1. Clone & Install

```bash
git clone https://github.com/ranvirdeshmukh2004/Playground.git
cd Playground
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Models

Edit `config.py` with your EC2 instance IPs:

```python
MODELS = {
    "llama-3.2-1b": {
        "name": "Llama 3.2 1B Instruct",
        "base_url": "http://YOUR_EC2_IP:8080",
        "endpoint": "/chat",
        "model_id": "meta-llama/Llama-3.2-1B-Instruct",
        "description": "Lightweight 1B model, fast for simple tasks.",
        "size": "1B",
        "context_len": 8192,
        "api_type": "custom",
    },
}
```

### 3. Run

```bash
python3 main.py
```

Open **http://localhost:7860** 🎉

---

## ☁️ Deploy to EC2 + Nginx (Production)

### Step 1: Launch a `t3.micro` EC2 instance (Ubuntu 24.04)

Open ports: **22** (SSH), **80** (HTTP), **443** (HTTPS)

### Step 2: SSH in and set up

```bash
ssh -i your-key.pem ubuntu@YOUR_IP

# Install dependencies
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git nginx supervisor

# Clone the repo
git clone https://github.com/ranvirdeshmukh2004/Playground.git ~/playground
cd ~/playground

# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Update config.py with Private IPs

Since the Playground is in the same VPC as your model instances, use **Private IPs** (they don't change on restart):

```bash
nano config.py
# Change base_url to Private IPs: "http://172.31.X.X:8080"
```

### Step 4: Set up Supervisor

```bash
sudo cp deploy/supervisor.conf /etc/supervisor/conf.d/playground.conf
sudo supervisorctl reread && sudo supervisorctl update
sudo supervisorctl start playground
```

### Step 5: Set up Nginx

```bash
sudo rm /etc/nginx/sites-enabled/default
sudo cp deploy/nginx.conf /etc/nginx/sites-available/playground
sudo ln -s /etc/nginx/sites-available/playground /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
```

### Step 6: Open `http://YOUR_EC2_IP` ✅

---

## 🖥 Model Server Setup (on each model EC2)

Each model EC2 instance runs `deploy/agent_api.py`:

```bash
# On each model EC2 instance:
sudo apt update && sudo apt install -y python3 python3-pip python3-venv
python3 -m venv ~/llm-env
source ~/llm-env/bin/activate
pip install torch transformers fastapi uvicorn

# Copy and edit agent_api.py (set MODEL variable)
# Then run in tmux:
tmux new -d -s api "source ~/llm-env/bin/activate && python3 ~/agent_api.py"
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serve the frontend UI |
| `GET` | `/api/models` | List all models with live status |
| `POST` | `/api/models` | Add a model at runtime |
| `DELETE` | `/api/models/{slug}` | Remove a model |
| `POST` | `/api/models/{slug}/test` | Test model connection |
| `POST` | `/api/chat` | Chat endpoint (SSE stream) |
| `POST` | `/v1/chat/completions` | OpenAI-compatible proxy |

### Curl Example

```bash
curl http://localhost:7860/api/chat \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.2-1b",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 512
  }'
```

### OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:7860/v1", api_key="not-needed")
response = client.chat.completions.create(
    model="llama-3.2-1b",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
)
for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

---

## 📊 Current Models

| Model | Size | EC2 Type | Inference |
|-------|------|----------|-----------|
| Llama 3.2 1B Instruct | 1B | t3.large | ~15-30s |
| Qwen 2.5 0.5B Instruct | 0.5B | t3.medium | ~5-10s |
| Gemma 2 2B IT | 2B | t3.large | ~30-60s |
| Phi-4 Mini Instruct | 3.8B | t3.xlarge | ~60-120s |

> Models run on CPU. For GPU inference (2-3s responses), use `g4dn` or `g5` instances.

---

## 🔒 Security

- No authentication built in — intended for private/internal use
- For production: add Nginx basic auth or put behind a VPN
- All model traffic stays within your AWS VPC (Private IPs)
- No data is sent to any external service

---

## 🛠 Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python, FastAPI, Uvicorn |
| Frontend | HTML, Vanilla JavaScript, Tailwind CSS |
| Model Loading | PyTorch, HuggingFace Transformers |
| Web Server | Nginx (reverse proxy) |
| Process Manager | Supervisor |
| Cloud | AWS EC2 |

---

## 📝 License

MIT — use it however you like.
