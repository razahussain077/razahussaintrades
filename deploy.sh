#!/usr/bin/env bash
set -e

# ============================================================
# SMC Crypto Signal Bot — One-Click Deploy Script
# Tested on: Ubuntu 24.04 / Digital Ocean 2GB RAM droplet
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════╗"
echo "║   SMC Crypto Signal Bot — Deploy         ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# Must run as root
[[ $EUID -ne 0 ]] && err "Please run as root: sudo bash deploy.sh"

REPO_URL="https://github.com/razahussain077/razahussaintrades.git"
INSTALL_DIR="/opt/razahussaintrades"

# ── Step 1: Update system ──────────────────────────────────
info "Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq curl wget git unzip ufw ca-certificates gnupg lsb-release
log "System updated"

# ── Step 2: Setup 2GB swap (critical for 2GB RAM server) ──
if ! swapon --show | grep -q /swapfile; then
    info "Creating 2GB swap file..."
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
    sysctl -p > /dev/null 2>&1
    log "2GB swap file created and activated"
else
    log "Swap already configured"
fi

# ── Step 3: Install Docker ─────────────────────────────────
if ! command -v docker &> /dev/null; then
    info "Installing Docker..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
        $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    log "Docker installed"
else
    log "Docker already installed"
fi

# ── Step 4: Install Docker Compose (standalone) ───────────
if ! command -v docker-compose &> /dev/null; then
    info "Installing Docker Compose..."
    COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep '"tag_name"' | cut -d'"' -f4)
    curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
        -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    log "Docker Compose installed (${COMPOSE_VERSION})"
else
    log "Docker Compose already installed"
fi

# ── Step 5: Clone or update repository ────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Updating existing repository..."
    cd "$INSTALL_DIR"
    git pull origin main || git pull origin master
    log "Repository updated"
else
    info "Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    log "Repository cloned to $INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── Step 6: Configure firewall ────────────────────────────
info "Configuring UFW firewall..."
ufw --force reset > /dev/null 2>&1
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
log "Firewall configured (ports 22, 80, 443 open)"

# ── Step 7: Set environment variables ─────────────────────
info "Setting up environment..."
cat > .env.production << EOF
DATABASE_URL=sqlite:///./data/trades.db
ENVIRONMENT=production
EOF

# Update docker-compose for production networking
SERVER_IP=$(curl -s https://ipecho.net/plain 2>/dev/null || echo "localhost")
log "Server IP: ${SERVER_IP}"

# ── Step 8: Build and start containers ────────────────────
info "Building Docker images (this may take 5-10 minutes)..."
docker-compose build --no-cache 2>&1 | tail -5
log "Docker images built"

info "Starting all services..."
docker-compose up -d
log "All services started"

# ── Step 9: Wait for services to be ready ─────────────────
info "Waiting for services to become ready..."
RETRIES=30
until curl -sf http://localhost/health > /dev/null 2>&1 || [ $RETRIES -eq 0 ]; do
    sleep 2
    ((RETRIES--))
done

if curl -sf http://localhost/health > /dev/null 2>&1; then
    log "Health check passed"
else
    warn "Health check did not respond — services may still be starting"
fi

# ── Step 10: Auto-restart on reboot ────────────────────────
info "Setting up auto-start on reboot..."
cat > /etc/systemd/system/smc-bot.service << EOF
[Unit]
Description=SMC Crypto Signal Bot
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable smc-bot.service
log "Auto-start service configured"

# ── Done! ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✅  SMC Bot Deployment Complete!                   ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║                                                      ║${NC}"
echo -e "${GREEN}║   Dashboard:  http://${SERVER_IP}                    ${NC}"
echo -e "${GREEN}║   API:        http://${SERVER_IP}/api/                ${NC}"
echo -e "${GREEN}║   Health:     http://${SERVER_IP}/health              ${NC}"
echo -e "${GREEN}║                                                      ║${NC}"
echo -e "${GREEN}║   Manage:  docker-compose -f ${INSTALL_DIR}/docker-compose.yml logs -f  ${NC}"
echo -e "${GREEN}║   Stop:    docker-compose -f ${INSTALL_DIR}/docker-compose.yml down     ${NC}"
echo -e "${GREEN}║   Restart: docker-compose -f ${INSTALL_DIR}/docker-compose.yml restart  ${NC}"
echo -e "${GREEN}║                                                      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
