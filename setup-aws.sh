#!/bin/bash
# ═══════════════════════════════════════════════════════
#  KANBAN SYNC — AWS EC2 Setup Script
#  Run this on a fresh EC2 instance (Ubuntu 22.04 / 24.04)
#
#  Usage:
#    git clone <your-repo-url> kanban-sync
#    cd kanban-sync
#    chmod +x setup-aws.sh
#    ./setup-aws.sh
# ═══════════════════════════════════════════════════════

set -e

echo "========================================"
echo "  Kanban Sync — AWS EC2 Setup"
echo "========================================"
echo ""

# ── 1. Install Docker ──
echo "[1/4] Installing Docker..."
if command -v docker &> /dev/null; then
    echo "  ✓ Docker already installed: $(docker --version)"
else
    sudo apt-get update -y
    sudo apt-get install -y ca-certificates curl gnupg lsb-release

    # Add Docker's official GPG key
    sudo install -m 0755 -d /etc/apt/keyrings
    if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
            sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        sudo chmod a+r /etc/apt/keyrings/docker.gpg
    fi

    # Add Docker repository
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin

    # Add current user to docker group (so no sudo needed)
    sudo usermod -aG docker $USER
    echo "  ✓ Docker installed: $(docker --version)"
fi

# ── 2. Install Docker Compose ──
echo ""
echo "[2/4] Checking Docker Compose..."
if docker compose version &> /dev/null; then
    echo "  ✓ Docker Compose available: $(docker compose version)"
else
    echo "  ✗ Docker Compose not found. Installing..."
    sudo apt-get install -y docker-compose-plugin
    echo "  ✓ Docker Compose installed: $(docker compose version)"
fi

# ── 3. Set up .env if it doesn't exist ──
echo ""
echo "[3/4] Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  ✓ Created .env from .env.example"
    echo "  ⚠  IMPORTANT: Edit .env and change DB_PASSWORD to something secure!"
    echo "     Run: nano .env"
else
    echo "  ✓ .env already exists"
fi

# ── 4. Build and start everything ──
echo ""
echo "[4/4] Building and starting containers..."
echo "  This may take 2-3 minutes on first run (downloading images, building app)..."
echo ""
sudo docker compose up -d --build

# Wait for containers to be ready
echo ""
echo "Waiting for containers to start..."
sleep 10

# Show status
echo ""
echo "========================================"
echo "  ✅ SETUP COMPLETE!"
echo "========================================"
echo ""
echo "Container status:"
sudo docker compose ps
echo ""

# Get the instance's public IP
PUBLIC_IP=$(curl -s http://checkip.amazonaws.com || echo "YOUR-EC2-PUBLIC-IP")
echo "Your app is now running on:"
echo ""
echo "  http://$PUBLIC_IP"
echo ""
echo "════════════════════════════════════════"
echo "  IMPORTANT NEXT STEPS:"
echo "════════════════════════════════════════"
echo ""
echo "1. AWS Security Group:"
echo "   Make sure port 80 (HTTP) is open for your EC2 instance."
echo "   Go to: EC2 Console → Security Groups → Edit Inbound Rules"
echo "   Add Rule: Type=HTTP, Port=80, Source=0.0.0.0/0"
echo ""
echo "2. Change the database password:"
echo "   Edit .env file and set a secure DB_PASSWORD"
echo "   Then run: sudo docker compose down && sudo docker compose up -d"
echo ""
echo "3. Useful commands:"
echo "   View logs:    sudo docker compose logs -f"
echo "   Restart:      sudo docker compose restart"
echo "   Stop:         sudo docker compose down"
echo "   Status:       sudo docker compose ps"
echo ""
echo "========================================"
