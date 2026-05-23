# 🚀 Private Model Playground

A beautiful, self-hosted LLM chat playground — similar to [Groq Console](https://console.groq.com/playground) — for interacting with your own models running on EC2 instances (via vLLM, TGI, Ollama, or any OpenAI-compatible API).

![Dark themed playground with sidebar, chat, and settings panel](https://img.shields.io/badge/UI-Dark_Theme-6366f1?style=for-the-badge)
![FastAPI backend](https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge)
![Streaming](https://img.shields.io/badge/Streaming-SSE-a855f7?style=for-the-badge)

---

## ✨ Features

| Feature | Status |
|---|---|
| Dark-themed, responsive UI | ✅ |
| Model selector sidebar with status badges | ✅ |
| Streaming responses (SSE) | ✅ |
| Markdown + syntax-highlighted code blocks | ✅ |
| System prompt configuration | ✅ |
| Temperature / Max Tokens / Top-P controls | ✅ |
| Copy message & code block buttons | ✅ |
| Regenerate last response | ✅ |
| OpenAI-compatible `/v1/chat/completions` proxy | ✅ |
| Automatic health-checks every 30 seconds | ✅ |
| Easy model registration (edit a Python dict) | ✅ |
| Mobile-responsive layout | ✅ |

---

## 📁 Project Structure

```
Playground/
├── main.py              # FastAPI application (backend + routes)
├── config.py            # Model registry — edit this to add models
├── requirements.txt     # Python dependencies
├── README.md            # You are here
├── static/
│   ├── css/
│   │   └── styles.css   # Custom dark-theme styles
│   └── js/
│       └── app.js       # Frontend JavaScript (chat, streaming, etc.)
└── templates/
    └── index.html       # Jinja2 HTML template (Tailwind + custom CSS)
```

---

## 🛠 Quick Start

### 1. Clone & install

```bash
cd Playground
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure your models

Open **`config.py`** and edit the `MODELS` dictionary:

```python
MODELS = {
    "llama-3.2-1b": {
        "name": "Llama 3.2 1B Instruct",
        "host": "10.0.1.10",       # ← your EC2 private IP
        "port": 8000,              # ← port the model is served on
        "model_id": "meta-llama/Llama-3.2-1B-Instruct",
        "description": "Lightweight 1B model, great for quick tasks.",
        "size": "1B",
        "context_len": 8192,
    },
    # Add more models below...
}
```

Each model needs:

| Field | Description |
|---|---|
| `name` | Display name in the UI |
| `host` | IP address / hostname of the EC2 instance |
| `port` | Port the model server listens on |
| `model_id` | Model identifier used by the backend (e.g., vLLM model name) |
| `description` | Short blurb shown on the model card |
| `size` | Parameter count label (e.g., `"8B"`, `"70B"`) |
| `context_len` | Maximum context window length |
| `api_base` | *(optional)* Override the full base URL instead of using `host:port` |

### 3. Run

```bash
python main.py
```

Or with Uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 7860 --reload
```

Visit **http://localhost:7860** 🎉

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serve the frontend |
| `GET` | `/api/models` | List all models with live status |
| `GET` | `/api/models/{slug}/status` | Health-check a single model |
| `POST` | `/api/chat` | Simplified chat (streams SSE) |
| `POST` | `/v1/chat/completions` | OpenAI-compatible proxy |

### Using the OpenAI-compatible endpoint

You can point any OpenAI SDK client at your playground:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:7860/v1",
    api_key="not-needed",
)

response = client.chat.completions.create(
    model="llama-3.2-1b",       # ← use the slug from config.py
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
)

for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

---

## 🖥 Model Server Setup (on EC2)

This playground proxies requests to your model servers. You can use any OpenAI-compatible server:

### vLLM (recommended)

```bash
pip install vllm
python -m vllm.entrypoints.openai.api_server \
    --model meta-llama/Llama-3.2-1B-Instruct \
    --host 0.0.0.0 \
    --port 8000
```

### Ollama

```bash
ollama serve    # default port 11434
```

For Ollama, set `api_base` in config:

```python
"my-ollama-model": {
    ...
    "api_base": "http://10.0.1.10:11434/v1",
}
```

### Text Generation Inference (TGI)

```bash
docker run --gpus all -p 8000:80 \
    ghcr.io/huggingface/text-generation-inference:latest \
    --model-id meta-llama/Llama-3.2-1B-Instruct
```

---

## 🔒 Security Notes

- This playground is designed for **private/internal use**. There is no authentication built in.
- For production, put it behind a reverse proxy (Nginx/Caddy) with HTTPS and basic auth.
- All requests are proxied server-side — model server ports don't need to be publicly accessible.

---

## 📝 License

MIT — use it however you like.
