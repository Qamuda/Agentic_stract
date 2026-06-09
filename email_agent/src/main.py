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
DAYS_BACK = 3  # You said you're changing this to 3

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

    # Standard email parser
    try:
        dt = parsedate_to_datetime(date_str)

        if dt:
            return dt.astimezone(timezone.utc)

    except Exception:
        pass

    # Flexible fallback parser
    try:
        dt = parser.parse(date_str)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

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

        return {
            "subject": subject.strip(),
            "from": from_addr.strip(),
            "date": date_str.strip(),
            "body": body[:1000]
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


def query_gemma(email_data):

    prompt = f"""Summarize this email in 3 sentence. What should the user do, if anything?

From: {email_data['from']}
Subject: {email_data['subject']}
Date: {email_data['date']}
Body: {email_data['body']}

two sentence summary:"""
    start1 = time.time()
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
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
    """NEW: Prepends entries so newest emails appear at top"""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

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

    parsed_dates = 0
    failed_dates = 0

    start_time = time.time()
    print("Starting email scan...")
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
        if not email_date:

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
    print(f"Found {len(new_emails)} new emails to process from the last {DAYS_BACK} days.")

    if not new_emails:
        print("Nothing new to do.")
        return

    # Sort newest first before processing
    new_emails.sort(key=lambda x: x['date_obj'], reverse=True)
    summary_header = f"# Email Summary - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

    total = len(new_emails)
    suspicious_entries = []
    summary_entries = []

    for i, email_item in enumerate(new_emails):
        email_start = time.time()
        email_data = email_item['data']
        print(f"\nProcessing {i + 1}/{total}: {email_data['subject'][:60]}")

        score, reasons = score_email(email_data)
        verdict = query_gemma(email_data)


        entry = {
            "score": score,
            "subject": email_data['subject'],
            "from": email_data['from'],
            "date": email_data['date'],
            "reasons": reasons,
            "verdict": verdict
        }

        if score >= 4:
            suspicious_entries.append(entry)
            logging.warning(f"FLAGGED: {score}/10 - {email_data['subject'][:50]}")
            print(f"⚠️ FLAGGED: {score}/10")
        else:
            summary_entries.append(entry)
            logging.info(f"CLEAN: {score}/10 - {email_data['subject'][:50]}")
            print(f"✓ CLEAN: {score}/10")

        email_end = time.time()
        print(f"Time: {email_end - email_start:.2f}s")

        processed.append({
            "id": email_item['id'],
            "subject": email_data['subject'],
            "date": email_data['date'],
            "processed_at": datetime.now(timezone.utc).isoformat()
        })


    # Prepend all at once so newest stays on top
    if summary_entries:
        prepend_to_md(SUMMARY_FILE, summary_entries, summary_header if not os.path.exists(SUMMARY_FILE) else "")
    if suspicious_entries:
        prepend_to_md(SUSPICIOUS_FILE, suspicious_entries)

    end_time = time.time()

    save_processed(processed)
    print(f"\n📂 Done!, took ⏱ {end_time - start_time:.2f} secs and {total} emails processed.")
    print(f"💾 Total in cache: {len(processed)}")
    print(f"📝 Check {SUMMARY_FILE} and {SUSPICIOUS_FILE}")


if __name__ == "__main__":
    scan_recent_email()