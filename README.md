# 🧠 Agentic Stack

> A growing collection of **local-first AI agents** — all powered by Ollama.  
> No cloud. No telemetry. Just your machine.

![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Ollama](https://img.shields.io/badge/ollama-local-000000)
![Privacy](https://img.shields.io/badge/privacy-first-green)

---

## 🧭 Philosophy

Every agent in this stack is designed to run **entirely on your device**, using local LLMs via Ollama. Your emails, calendar, research, trades, and knowledge — all stay on your machine, under your control.

---

## 🤖 Agents

### ✅ Active

| Agent | Description | Status |
|-------|-------------|--------|
| **Email Agent** | Summarization & phishing detection for Thunderbird mailboxes | ✅ Live |
| **ARIA** | Privacy-first behavioral intelligence assistant | 🚧 In development |

### 🧪 Planned

| Agent | Description |
|-------|-------------|
| **Calendar Agent** | Smart scheduling & routine-aware time management |
| **Research Agent** | Local deep-dive research assistant with source tracking |
| **Trading Agent** | On-device market analysis & trade idea generation |
| **Knowledge Agent** | Personal knowledge base with local vector search |

---

## 🛠 Tech Stack

| Category   | Tools / Models |
|------------|----------------|
| Language   | Python         |
| Inference  | Ollama         |
| Models     | Gemma, Qwen, DeepSeek |
| Data       | Thunderbird, Markdown, JSON |
| Storage    | Local filesystem, SQLite (planned) |

---

## 📂 Structure (suggested)
agentic-stack/
├── email-agent/ # Email summarization & phishing detector
├── calendar-agent/ # (planned)
├── research-agent/ # (planned)
├── trading-agent/ # (planned)
├── knowledge-agent/ # (planned)
└── README.md

text

---

## 🚀 Getting Started

1. Install [Ollama](https://ollama.com) and pull your desired models:
   ```bash
   ollama pull gemma3:4b
   ollama pull qwen3:8b
   ollama pull deepseek-r1:8b
Clone this repo and navigate into an agent’s directory.

Follow each agent’s individual README for setup and usage.

📌 Roadmap
Email Agent

ARIA – adaptive behavioral intelligence

Calendar Agent – time intelligence

Research Agent – local deep-dive assistant

Trading Agent – on-device market reasoning

Knowledge Agent – personal knowledge graph

Centralized dashboard (optional)

Cross-agent communication layer

🤝 Contributing
All agents are open-source and built for privacy. If you’ve got an idea for a new local-first agent, feel free to open an issue or a PR.

📄 License
This stack is available under the MIT License.
Each agent may carry its own license — check individual directories.