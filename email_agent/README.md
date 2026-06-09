# 📧 Email Agent

> Local AI-powered email summarization and phishing detection — fully on-device.

![Status](https://img.shields.io/badge/status-work_in_progress-yellow)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Ollama](https://img.shields.io/badge/ollama-local-000000)
![Privacy](https://img.shields.io/badge/privacy-first-green)

---

## 🔍 Overview

Email Agent reads emails directly from a local **Thunderbird** mailbox, analyzes them using local **Ollama** models, generates concise summaries, and flags potentially suspicious messages.

Everything runs on your machine — **no cloud, no telemetry, no API keys needed.**

---

## ✨ Features

- 📬 **Local email processing** – works directly with Thunderbird mailbox files
- 🧠 **AI-generated summaries** – powered by local LLMs via Ollama
- 🛡️ **Rule-based phishing detection** – scores emails for suspicious patterns
- 📝 **Markdown summary reports** – daily digests you can read anywhere
- 🗂️ **Processed-email tracking cache** – avoids duplicate work
- 🔒 **Fully offline operation** – privacy by design

---

## 🧪 Models Tested

| Model       | Size | Notes                     |
|-------------|------|---------------------------|
| Gemma 3 1B  | 1B   | Fast, lightweight         |
| Gemma 3 4B  | 4B   | Good balance              |
| Qwen3 8B    | 8B   | Highest quality summaries |

---

## ⚙️ Current Workflow

1. Load emails from Thunderbird mailbox
2. Extract sender, subject, date, body, and links
3. Filter emails by date range
4. Score phishing risk
5. Generate AI summary through Ollama
6. Save results to Markdown reports
7. Cache processed emails (so you never re-read the same one twice)

---

## 📂 Example Output

```markdown
**Subject:** Weekly Team Meeting

**Summary:**
Meeting moved from Thursday to Friday at 2 PM.

**Action Needed:**
Update calendar.

**Priority:**
Low
🛠 Tech Stack
Technology	Role
Python	Core scripting
Ollama	Local LLM inference
Thunderbird	Mailbox data source
Markdown	Report format
JSON	Processed-email cache
🚧 Roadmap
✅ Phase 1 — Foundation (done)
Email extraction from Thunderbird

Local summarization via Ollama

Rule-based phishing scoring

🚧 Phase 2 — Intelligence Upgrades (in progress)
Live mailbox monitoring (watch for new emails)

Improved phishing detection (heuristic + ML)

Multi-model benchmarking and selection

🔮 Phase 3 — Integration
Connect with ARIA (Adaptive Routine Intelligence Assistant)

Local vector search for historical email lookup

Behavioral intelligence workflows (learn from email habits)

📌 Status
🟡 Work in progress
Currently testing on personal Gmail before rolling out to Outlook and university accounts.

📄 License
This project is open-source under the MIT License.
Built with the belief that your email should stay on your machine, not someone else's server.