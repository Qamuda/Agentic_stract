import os
import json
import mailbox
import requests
import hashlib
from email.header import decode_header, make_header
import logging
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from dateutil import parser
import time

# === CONFIG ===
THUNDERBIRD_INBOX = os.path.expanduser(r"C:\Users\Admin\AppData\Roaming\Thunderbird\Profiles\7you0l9t.default-release\ImapMail\imap.gmail.com\INBOX")
PROCESSED_FILE = "processed_emails.json"
SUMMARY_FILE = "summary.md"
SUSPICIOUS_FILE = "suspicious.md"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:1b"
DAYS_BACK = 2  # You said you're changing this to 3

# === LOGGING ===
logging.basicConfig(
    filename='email_agent.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
## print(f"Log file: {os.path.abspath('email_agent.log')}")


def parse_email_date(date_str):

    if not date_str:
        return None

    # Standard email format
    try:
        dt = parsedate_to_datetime(date_str)

        if dt:
            return dt.astimezone(timezone.utc)

    except Exception:
        pass

    # Thunderbird weird formats
    try:
        dt = datetime.strptime(
            date_str,
            "%Y.%m.%d-%H.%M.%S"
        )

        return dt.replace(
            tzinfo=timezone.utc
        )

    except Exception:
        pass

    # Another weird Thunderbird format
    try:
        dt = datetime.strptime(
            date_str,
            "%Y.%m.%d.%H.%M"
        )

        return dt.replace(
            tzinfo=timezone.utc
        )

    except Exception:
        pass

    # Flexible parser fallback
    try:
        dt = parser.parse(date_str)

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:
        logging.warning(
            f"Unable to parse date: {date_str}"
        )

    return None

def make_email_id(email_data):
    unique_str = f"{email_data['subject']}|{email_data['date']}|{email_data['from']}"
    return hashlib.md5(unique_str.encode('utf-8')).hexdigest()


def load_processed():
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_processed(processed_list):
    with open(PROCESSED_FILE, 'w', encoding='utf-8') as f:
        json.dump(processed_list, f, indent=2)


def load_mbox_emails():
    try:
        print(f"Loading emails from: {THUNDERBIRD_INBOX}")
        if not os.path.exists(THUNDERBIRD_INBOX):
            print(f"ERROR: INBOX file not found at {THUNDERBIRD_INBOX}")
            return []
        mbox = mailbox.mbox(THUNDERBIRD_INBOX)
        emails = []
        for key, msg in mbox.items():
            emails.append({"key": key, "msg": msg})
        print(f"Loaded {len(emails)} total emails from mbox")
        return emails
    except Exception as e:
        logging.error(f"Failed to load mbox: {e}")
        print(f"ERROR: Failed to load mbox: {e}")
        return []


def extract_email_data(msg):
    try:
        subject = str(make_header(decode_header(msg['Subject'] or "(No Subject)")))
        from_addr = str(make_header(decode_header(msg['From'] or "(Unknown Sender)")))
        date_str = msg['Date'] or ""

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode('utf-8', errors='ignore')
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode('utf-8', errors='ignore')

        if len(body) > 600:
            body = body[:300] + "\n...\n" + body[-300:]

        return {
            "subject": subject.strip(),
            "from": from_addr.strip(),
            "date": date_str.strip(),
            "body": body
        }
    except Exception as e:
        logging.error(f"Failed to extract email data: {e}")

        return None


def score_email(email_data):
    score = 0
    reasons = []
    subject_lower = email_data['subject'].lower()
    body_lower = email_data['body'].lower()

    suspicious_keywords = ['urgent', 'verify', 'suspended', 'click here', 'act now', 'limited time', 'password']
    for keyword in suspicious_keywords:
        if keyword in subject_lower or keyword in body_lower:
            score += 2
            reasons.append(f"Suspicious keyword: {keyword}")

    return score, reasons

def should_skip_llm(email_data):
    subject = email_data["subject"].lower()
    body = email_data["body"]

    # Very short emails
    if len(body.strip()) < 50:
        return True, "Very little text content"

    # Mostly links
    link_count = body.count("http")
    if link_count > 10:
        return True, "Link-heavy marketing email"

    # Wallpaper emails
    wallpaper_keywords = [
        "wallpaper",
        "one piece",
        "anime wallpaper"
    ]

    if any(k in subject for k in wallpaper_keywords):
        return True, "Wallpaper email"

    # Store promotions
    promo_keywords = [
        "new arrivals",
        "shop now",
        "limited time",
        "sale",
        "collection"
    ]

    if any(k in subject for k in promo_keywords):
        return True, "Promotional email"

    if "pinterest" in email_data["from"].lower():
        return True, "Pinterest"

    if "bestbuy" in email_data["from"].lower():
        return True, "Retail promotion"

    return False, None


def query_gemma(email_data):

    message = f"""
You are an email classifier.

Return ONLY this exact format:

Subject: <email subject>
Summary:
<Mention the most important products,
topics, offers, or announcements
mentioned in the email.
Be decisive and specific.

Write 2-4 concise sentences describing the most important points.>

Action Required: <comma-separated list of required actions, or "None">
Deadline: <explicit date/time IF present; otherwise "None">
Priority: <High, Medium, Low>

Rules:
- Use the email date only to understand relative time words like today, tomorrow, this week, or next week.
- Do not calculate future dates unless they are explicitly stated.
- If there is no clear deadline, write "None".
- If the email does not require the user to do anything, write "None" for Action Required.
- Choose the earliest required deadline if more than one appears.
- High = interviews, school deadlines, financial alerts, account/security issues, urgent requests, anything due within 24 hours.
- Medium = meetings, project updates, team communications, requests with a clear deadline beyond 24 hours.
- Low = newsletters, promotions, marketing, social notifications, informational emails with no action.
- Keep responses concise.
- Do not explain reasoning.
- Do not add extra text.

Email Date: {email_data['date']}
From: {email_data['from']}
Subject: {email_data['subject']}
Body: {email_data['body']}
"""
    start1 = time.time()
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": message,
            "stream": False
        }, timeout=150)

        if response.status_code == 200:
            return response.json()['response'].strip()
        else:
            logging.error(f"Ollama error: {response.status_code}")
            return "Could not generate summary - Ollama error"

    except Exception as e:
        logging.error(f"Gemma query failed: {e}")
        return "Could not generate summary - connection failed"

    finally:
        end1 = time.time()
        print(f"Gemma Time: {end1 - start1:.2f}s")



def prepend_to_md(filepath, entries, header=""):
    """NEW: Prepends entries as newest emails appear at top"""
    print(f"Writing {len(entries)} entries to {filepath}")
    directory = os.path.dirname(filepath)

    if directory:
        os.makedirs(directory, exist_ok=True)

    existing_content = ""
    file_exists = os.path.exists(filepath)
    if file_exists:
        with open(filepath, 'r', encoding='utf-8') as f:
            existing_content = f.read()

    with open(filepath, 'w', encoding='utf-8') as f:
        if header and not file_exists:
            f.write(header)

        # Write new entries first = newest at top
        for e in entries:
            f.write(f"## {e['score']}/10 - {e['subject']}\n")
            f.write(f"**From:** `{e['from']}` \n")
            f.write(f"**Date:** {e['date']} \n")
            f.write(f"**Reasons:** {', '.join(e['reasons']) if e['reasons'] else 'None'} \n")
            f.write(f"**Summary:** {e['verdict']}\n\n")
            f.write("---\n\n")

        # Then write old content
        if existing_content:
            f.write(existing_content)


def scan_recent_email():
    skipped_llm = 0
    parsed_dates = 0
    failed_dates = 0

    start_time = time.time()
    print(f"Starting email scan, using Model: {MODEL}")
    processed = load_processed()
    processed_ids = {p['id'] for p in processed}
    print(f"Already processed {len(processed_ids)} emails before")

    mbox_emails = load_mbox_emails()
    if not mbox_emails:
        print("No emails found. Check Thunderbird path and make sure Thunderbird is closed.")
        return

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    print(f"Looking for emails newer than {cutoff_date.strftime('%Y-%m-%d %H:%M UTC')}")

    new_emails = []
    skipped = 0
    for item in mbox_emails:
        email_data = extract_email_data(item['msg'])
        if not email_data:
            continue

        email_id = make_email_id(email_data)

        if email_id in processed_ids:
            skipped += 1
            continue

        email_date = parse_email_date(email_data['date'])
        if email_date:
            parsed_dates += 1
        else:
            failed_dates += 1
            continue

        if email_date > cutoff_date:
            new_emails.append({
                "id": email_id,
                "data": email_data,
                "date_obj": email_date
            })

    if skipped > 0:
        print(f"Skipped {skipped} emails already processed")

    print(f"Parsed Dates: {parsed_dates}")
    print(f"Failed Dates: {failed_dates}")
    #print(f"Found {len(new_emails)} new emails to process from the last {DAYS_BACK} days.")

    # Sort newest first before processing
    new_emails.sort(key=lambda x: x['date_obj'], reverse=True)
    summary_header = f"# Email Summary - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

    total = len(new_emails)
    suspicious_entries = []
    summary_entries = []

    for i, email_item in enumerate(new_emails):
        email_start = time.time()

        email_data = email_item["data"]

        print(f"\nProcessing {i + 1}/{total}: {email_data['subject'][:60]}")

        # ----------------------------
        # Phishing Score
        # ----------------------------
        score, reasons = score_email(email_data)

        # ----------------------------
        # Email Stats
        # ----------------------------
        body_length = len(email_data["body"])
        print(f"Body Length: {body_length}")

        # ----------------------------
        # LLM Decision
        # ----------------------------
        skip, reason = should_skip_llm(email_data)

        if skip:
            verdict = f"Skipped LLM - {reason}"
            skipped_llm += 1
            print(f"LLM Skipped: {reason}")

        else:
            verdict = query_gemma(email_data)

        # ----------------------------
        # Build Result Entry
        # ----------------------------
        entry = {
            "score": score,
            "subject": email_data["subject"],
            "from": email_data["from"],
            "date": email_data["date"],
            "reasons": reasons,
            "verdict": verdict
        }

        # ----------------------------
        # Sort Clean vs Suspicious
        # ----------------------------
        if score >= 4:

            suspicious_entries.append(entry)

            logging.warning(
                f"FLAGGED: {score}/10 - {email_data['subject'][:50]}"
            )

            print(f"⚠️ FLAGGED: {score}/10")

        else:

            summary_entries.append(entry)

            logging.info(
                f"CLEAN: {score}/10 - {email_data['subject'][:50]}"
            )

            print(f"✓ CLEAN: {score}/10")

        # ----------------------------
        # Cache Processed Email
        # ----------------------------
        processed.append({
            "id": email_item["id"],
            "subject": email_data["subject"],
            "date": email_data["date"],
            "processed_at": datetime.now(timezone.utc).isoformat()
        })

        email_end = time.time()

        print(f"Time: {email_end - email_start:.2f}s")

    print(f"Summary Entries: {len(summary_entries)}")
    print(f"Suspicious Entries: {len(suspicious_entries)}")
    save_processed(processed)


    # Prepend all at once as newest stays on top
    if summary_entries:
        prepend_to_md(SUMMARY_FILE, summary_entries, summary_header if not os.path.exists(SUMMARY_FILE) else "")
    if suspicious_entries:
        prepend_to_md(SUSPICIOUS_FILE, suspicious_entries)

    end_time = time.time()

    print(f"\n📂 Done!, took ⏱ {end_time - start_time:.2f} secs and {total} emails processed.")
    print(f"🤖 LLM Calls Skipped: {skipped_llm}")
    print(f"💾 Total in cache: {len(processed)}")
    print(f"📝 Check {SUMMARY_FILE} and {SUSPICIOUS_FILE}")


if __name__ == "__main__":
    scan_recent_email()