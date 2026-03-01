# 🐋 SMC Crypto Signal Bot

A **world-class, production-ready crypto trading signal bot** built on **Smart Money Concepts (SMC)** and **ICT (Inner Circle Trader)** methodology. Designed to think like a Market Maker, not a retail trader.

**All data sourced from FREE public APIs — no API keys required.**

---

## 🔥 Features

### Analysis Engines
| Engine | What it detects |
|--------|----------------|
| **Smart Money Concepts** | Order Blocks, Fair Value Gaps, BOS, CHoCH, Premium/Discount Zones |
| **ICT Methodology** | Kill Zones (PKT), OTE (61.8–78.6% fib), Judas Swing, Silver Bullet, Power of 3 |
| **Liquidity Mapping** | Equal Highs/Lows, Stop Hunts, Liquidity Sweeps & Reclaims, Voids |
| **Wyckoff Analysis** | Accumulation/Distribution phases, Spring, Upthrust |
| **Whale Tracking** | Abnormal volume (3× avg), volume divergence, order book imbalance |
| **Correlation Engine** | BTC dominance, BTC–ALT correlation, volatility ranking |
| **Multi-Timeframe** | 1m → 1W confluence scoring, trend bias detection |

### Dashboard
- 📊 Real-time price updates via WebSocket (Binance)
- 🎯 Complete signal cards: Entry zone, SL, TP1/TP2/TP3, leverage, liquidation price
- ⏰ Kill Zone timer in **Pakistan Time (PKT UTC+5)**
- 📈 TradingView Lightweight Charts with SMC overlays
- 🛡️ Anti-liquidation system with dynamic leverage calculator
- 💼 Portfolio tracker with PnL history
- 🔔 Browser notifications for new signals

### Signal Output
```
Type: LONG or SHORT
Coin: e.g., ETH/USDT
Exchange: Which exchange shows best setup
Timeframe: Primary timeframe
Entry Zone: Price range (not single price)
Stop Loss: With % from entry
Take Profit 1/2/3: With position sizing (40%/35%/25%)
Recommended Leverage: Anti-liquidation calculation
Liquidation Price: Always far from entry
Risk/Reward: Minimum 1:2
Confidence Score: 0–100% (SMC + ICT + Liquidity + Wyckoff + MTF)
Setup Type: e.g., "Liquidity Sweep + OB Retest + FVG Fill"
Reasoning: 3–5 bullet points
Invalidation: When signal is no longer valid
Kill Zone: Session at signal creation
```

---

## 🔧 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, WebSockets |
| Frontend | Next.js 14, TailwindCSS, lightweight-charts |
| Database | SQLite (optimized for 2GB RAM) |
| Deployment | Docker, docker-compose, Nginx |

### Free Data Sources (No API Keys)
| Data | Source |
|------|--------|
| Live Prices + WebSocket | Binance Public API |
| Klines / Candles | Binance, Bybit, OKX |
| Funding Rate + Open Interest | Binance Futures Public |
| Order Book Depth | Binance Public |
| Market Cap / Coin List | CoinGecko Free API |
| Global Market Data | CoinGecko Free API |

---

## 🚀 Quick Deploy (Digital Ocean Ubuntu 24.04)

```bash
# One command — installs everything and starts the bot
curl -fsSL https://raw.githubusercontent.com/razahussain077/razahussaintrades/main/deploy.sh | sudo bash
```

Or clone and run manually:

```bash
git clone https://github.com/razahussain077/razahussaintrades.git
cd razahussaintrades
sudo bash deploy.sh
```

After deployment, open: **http://YOUR_SERVER_IP**

---

## 🏗️ Local Development

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker & docker-compose (optional for local)

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API available at: http://localhost:8000
Docs at: http://localhost:8000/docs

### Frontend
```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_WS_URL=ws://localhost:8000 \
npm run dev
```

Dashboard at: http://localhost:3000

### Full stack with Docker
```bash
docker-compose up --build
```

---

## 📁 Project Structure

```
razahussaintrades/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entry point
│   │   ├── config.py               # Settings, PKT timezone
│   │   ├── websocket_manager.py    # WebSocket handler
│   │   ├── exchanges/              # Binance, Bybit, OKX, CoinGecko clients
│   │   ├── analysis/               # 7 analysis engines (SMC, ICT, ...)
│   │   ├── signals/                # Signal generator + confidence scorer
│   │   ├── risk/                   # Anti-liquidation + position sizing
│   │   ├── api/                    # REST + WebSocket routes
│   │   └── database/               # SQLite (aiosqlite)
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── app/                        # Next.js 14 App Router pages
│   ├── components/                 # React components
│   ├── hooks/                      # useWebSocket, useLivePrices, useSignals
│   ├── lib/                        # API client, types, utils
│   └── Dockerfile
│
├── nginx/nginx.conf                # Reverse proxy
├── docker-compose.yml              # Full stack composition
├── deploy.sh                       # One-click deploy script
└── README.md
```

---

## 🛡️ Anti-Liquidation System

The #1 priority is to **never get liquidated**.

### Dynamic Leverage Formula
```
distance = |entry_price - nearest_liquidity_zone| / entry_price
max_safe_leverage = (distance × 100) / 1.5
recommended_leverage = max_safe_leverage × 0.5   (use only 50% of max)
cap: 20×
```

### Position Sizing
```
risk_amount = portfolio × risk_pct          (default 1–2%)
position_size = risk_amount / |entry - SL|
```

### Safety Rules
- Max portfolio risk at any time: **5%**
- Max **3 correlated positions** open simultaneously
- Stop loss triggers **before** liquidation price
- Funding rate warnings at ±0.1%

---

## ⚙️ Configuration

### Backend `.env`
```env
DATABASE_URL=sqlite:///./data/trades.db
ENVIRONMENT=production
```

### Frontend environment variables
```env
NEXT_PUBLIC_API_URL=http://your-server-ip
NEXT_PUBLIC_WS_URL=ws://your-server-ip
```

Set these in `docker-compose.yml` before deploying.

---

## 📡 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/coins` | All coins with prices and signals |
| GET | `/api/coins/{symbol}` | Detailed coin data |
| GET | `/api/signals` | Active signals |
| GET | `/api/signals/{id}` | Specific signal |
| GET | `/api/market/overview` | Market cap, BTC dominance, fear/greed |
| GET | `/api/market/kill-zones` | Kill zone timings (PKT) |
| GET | `/api/risk/calculate` | Leverage + position size calculator |
| POST | `/api/portfolio/settings` | Save portfolio settings |
| GET | `/api/portfolio/settings` | Get portfolio settings |
| POST | `/api/signals/{id}/take` | Mark signal as taken |
| GET | `/api/correlation` | BTC–ALT correlation matrix |
| WS | `/ws/prices` | Live price stream |
| WS | `/ws/signals` | Live signal updates |
| WS | `/ws/market` | Market overview updates |

Full interactive docs: `http://your-server/docs`

---

## 🕐 Kill Zones (Pakistan Time / PKT = UTC+5)

| Session | PKT Time | UTC Time |
|---------|----------|----------|
| 🟦 Asian | 05:00 – 14:00 | 00:00 – 09:00 |
| 🟧 London | 13:00 – 17:00 | 08:00 – 12:00 |
| 🟩 New York | 18:00 – 23:00 | 13:00 – 18:00 |
| 🟪 London Close | 22:00 – 00:00 | 17:00 – 19:00 |

---

## 🖥️ Server Requirements

Optimized for **Digital Ocean 2GB RAM droplet** (SGP1 Singapore):
- Backend: ≤ 512 MB RAM
- Frontend: ≤ 512 MB RAM
- Nginx: ≤ 64 MB RAM
- OS + headroom: ~512 MB
- **2 GB swap file** auto-configured by deploy.sh

---

## 🔒 Security

- No API keys committed to the repository
- All external data from public, unauthenticated endpoints
- Rate limiting on API via Nginx (30 req/min)
- Input validation via Pydantic
- XSS / clickjacking protection headers via Nginx
- UFW firewall configured by deploy.sh (ports 22, 80, 443)

---

## ⚠️ Disclaimer

This software is for **educational and informational purposes only**. Cryptocurrency trading involves significant risk. Past performance does not guarantee future results. Always do your own research (DYOR) and never trade with money you cannot afford to lose.