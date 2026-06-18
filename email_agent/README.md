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
## 📊 Performance Notes


Gemma 3 1B

Selected because it offers the best balance between speed and usefulness during local testing.

Typical Processing Times
Email Size	Average Time
Short email	3–8 seconds
~600 chars	10–20 seconds
Complex newsletters	Can vary significantly
Optimizations Implemented
Body truncation before LLM processing
Processed email caching
Promotional email skipping
Low-content email skipping
Ollama request timeout protection
🚧 Known Limitations
Markdown Report Generation

Under investigation:

Processed emails are correctly stored in processed_emails.json
Some testing runs did not update summary.md as expected
Initial file path issue was identified and corrected
Additional validation is ongoing
Phishing Detection

Current phishing scoring is rule-based and intended as a first-pass warning system.

Future versions may incorporate:

Reputation analysis
Sender profiling
ML-assisted classification


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
✅ Phase 1 — Foundation (mostly complete)

Email extraction from Thunderbird
Local summarization via Ollama
Rule-based phishing scoring
Processed-email cache
Date parsing improvements for Thunderbird formats
LLM skip logic for promotional and low-content emails
Runtime optimization and timeout protection


🟡 Current Status
The Email Agent is operational and processing recent Thunderbird emails successfully.
Processed-email caching is working across runs, and recent tests show that previously processed emails are being skipped correctly.
The main remaining V1 work is around markdown report behavior, ordering consistency, and validating Thunderbird-specific date semantics.

🚧 Phase 2 — Intelligence Upgrades (in progress)
Live mailbox monitoring
New-email polling mode
Improved phishing detection
Structured action item extraction
Better priority classification
Sender reputation analysis
Multi-model benchmarking and selection
Recent Improvements
Switched from Gemma 3 4B to Gemma 3 1B for significantly faster processing
Added processed email cache to prevent duplicate summarization
Improved prompt structure for:
Summary
Action Required
Deadline
Priority
Added Thunderbird-specific date parsing support
Added LLM skip detection for:
Wallpapers
Promotional emails
Low-text emails
Added Ollama request timeout protection
Added body truncation optimization to reduce inference time

📌 Status
🟡 Work in progress
Currently testing on personal Gmail before rolling out to Outlook and university accounts.

📄 License
This project is open-source under the MIT License.
Built with the belief that your email should stay on your machine, not someone else's server.