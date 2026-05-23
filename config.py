"""
Model Configuration — Runtime registry seeded from this file.
Models can also be added/removed via the web UI (+ Add Model button).
"""

MODELS: dict[str, dict] = {
    "llama-3.2-1b": {
        "name": "Llama 3.2 1B Instruct",
        "base_url": "http://13.234.114.58:8080",
        "endpoint": "/chat",
        "model_id": "meta-llama/Llama-3.2-1B-Instruct",
        "description": "Lightweight 1B model, fast for simple tasks.",
        "size": "1B",
        "context_len": 8192,
        "api_type": "custom",
    },
    "qwen-2.5-0.5b": {
        "name": "Qwen 2.5 0.5B Instruct",
        "base_url": "http://13.235.254.245:8080",
        "endpoint": "/chat",
        "model_id": "Qwen/Qwen2.5-0.5B-Instruct",
        "description": "Ultra-lightweight 0.5B model, fastest responses.",
        "size": "0.5B",
        "context_len": 32768,
        "api_type": "custom",
    },
    "gemma-2-2b": {
        "name": "Gemma 2 2B IT",
        "base_url": "http://13.232.241.170:8080",
        "endpoint": "/chat",
        "model_id": "google/gemma-2-2b-it",
        "description": "Google's capable 2B model, great balance of quality and speed.",
        "size": "2B",
        "context_len": 8192,
        "api_type": "custom",
    },
    "phi-4-mini": {
        "name": "Phi-4 Mini Instruct",
        "base_url": "http://13.201.106.104:8080",
        "endpoint": "/chat",
        "model_id": "microsoft/Phi-4-mini-instruct",
        "description": "Microsoft's 3.8B reasoning model, strong for logic and code.",
        "size": "3.8B",
        "context_len": 131072,
        "api_type": "custom",
    },
}
