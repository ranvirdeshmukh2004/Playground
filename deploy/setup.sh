#!/bin/bash
# ────────────────────────────────────────────────────────────────
# Playground EC2 Setup Script
# Run this on a fresh Ubuntu 24.04 EC2 instance to deploy the
# Private Model Playground with Nginx + Supervisor.
# ────────────────────────────────────────────────────────────────

set -e

REPO_URL="https://github.com/ranvirdeshmukh2004/Playground.git"
APP_DIR="/home/ubuntu/playground"

echo "══════════════════════════════════════════"
echo "  Private Model Playground — Setup"
echo "══════════════════════════════════════════"

# 1. System packages
echo "[1/6] Installing system packages..."
sudo apt update -qq
sudo apt install -y python3 python3-pip python3-venv git nginx supervisor

# 2. Clone repo
echo "[2/6] Cloning repository..."
if [ -d "$APP_DIR" ]; then
    echo "  Directory exists, pulling latest..."
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# 3. Python environment
echo "[3/6] Setting up Python environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet -r requirements.txt

# 4. Supervisor
echo "[4/6] Configuring Supervisor..."
sudo cp deploy/supervisor.conf /etc/supervisor/conf.d/playground.conf
sudo supervisorctl reread
sudo supervisorctl update

# 5. Nginx
echo "[5/6] Configuring Nginx..."
sudo rm -f /etc/nginx/sites-enabled/default
sudo cp deploy/nginx.conf /etc/nginx/sites-available/playground
sudo ln -sf /etc/nginx/sites-available/playground /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx

# 6. Start
echo "[6/6] Starting Playground..."
sudo supervisorctl start playground 2>/dev/null || sudo supervisorctl restart playground

echo ""
echo "══════════════════════════════════════════"
echo "  ✅ Playground is live!"
echo "  Open: http://$(curl -s ifconfig.me)"
echo ""
echo "  Next: edit config.py with your model IPs"
echo "  Then: sudo supervisorctl restart playground"
echo "══════════════════════════════════════════"
