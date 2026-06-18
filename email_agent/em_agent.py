import os
import json
import mailbox
import requests
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import logging

# === CONFIG ===
THUNDERBIRD_INBOX = os.path.expanduser("~\\AppData\\Roaming\\Thunderbird\\Profiles\\YOUR_PROFILE\\ImapMail\\imap.gmail.com\\INBOX")
PROCESSED_FILE = "processed_emails.json"
SUMMARY_FILE = "summary.md"
SUSPICIOUS_FILE = "suspicious.md"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3"
DAYS_BACK = 2 # Change to 30 for debugging

# === LOGGING ===
logging.basicConfig(
    filename='email.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
print(f"Log file: {os.path.abspath('email.log')}")

def parse_email_date(date_str):
    """Parse email date and convert to UTC-naive for comparison"""
    try:
        dt = parsedate_to_datetime(date_str)
        if dt:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return None
    except:
        return None

def load_processed():
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, 'r') as f:
            return json.load(f)
    return []

def save_processed(processed_list):
    with open(PROCESSED_FILE, 'w') as f:
        json.dump(processed_list, f, indent=2)

def load_mbox_emails():
    try:
        mbox = mailbox.mbox(THUNDERBIRD_INBOX)
        emails = []
        for key, msg in mbox.items():
            emails.append({"key": key, "msg": msg})
        return emails
    except Exception as e:
        logging.error(f"Failed to load mbox: {e}")
        return []

def extract_email_data(msg):
    """Extract subject, from, date, body from email message"""
    try:
        subject = msg['Subject'] or "(No Subject)"
        from_addr = msg['From'] or "(Unknown Sender)"
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
            "subject": subject,
            "from": from_addr,
            "date": date_str,
            "body": body[:600] # Limit body to 1000 chars for Ollama
        }
    except Exception as e:
        logging.error(f"Failed to extract email data: {e}")
        return None

def score_email(email_data):
    """Simple heuristic scoring before AI"""
    score = 0
    reasons = []

    subject_lower = email_data['subject'].lower()
    from_lower = email_data['from'].lower()

    suspicious_keywords = ['urgent', 'verify', 'suspended', 'click here', 'act now', 'limited time']
    for keyword in suspicious_keywords:
        if keyword in subject_lower or keyword in email_data['body'].lower():
            score += 2
            reasons.append(f"Suspicious keyword: {keyword}")

    if 'noreply' not in from_lower and '@' not in from_lower:
        score += 1
        reasons.append("Odd sender format")

    return score, reasons

def query_gemma(email_data):
    """Send email to Gemma for summary"""
    prompt = f"""Summarize this email in 1 sentence. Focus on what action the user should take, if any.

From: {email_data['from']}
Subject: {email_data['subject']}
Date: {email_data['date']}
Body: {email_data['body']}

Summary:"""


    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        }, timeout=30)

        if response.status_code == 200:
            return response.json()['response'].strip()
        else:
            logging.error(f"Ollama error: {response.status_code}")
            return "Failed to generate summary"
    except Exception as e:
        logging.error(f"Gemma query failed: {e}")
        return "Failed to generate summary"

def append_to_md(filepath, entries, header=""):
    """Simple append - newest will be at bottom for now"""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

    mode = 'a' if os.path.exists(filepath) else 'w'
    with open(filepath, mode, encoding='utf-8') as f:
        if header and mode == 'w':
            f.write(header)

        for e in entries:
            f.write(f"## {e['score']}/10 - {e['subject']}\n")
            f.write(f"**From:** `{e['from']}` \n")
            f.write(f"**Date:** {e['date']} \n")
            f.write(f"**Reasons:** {', '.join(e['reasons']) if e['reasons'] else 'None'} \n")
            f.write(f"**Summary:** {e['verdict']}\n\n")
            f.write("---\n\n")

def scan_recent_email():
    processed = load_processed()
    processed_keys = {p['key'] for p in processed}

    mbox_emails = load_mbox_emails()
    if not mbox_emails:
        print("No emails found or failed to load mbox")
        return

    cutoff_date = datetime.now() - timedelta(days=DAYS_BACK)
    print(f"DEBUG: cutoff_date = {cutoff_date}")
    print(f"DEBUG: Looking for emails newer than {cutoff_date}")

    new_emails = []
    for item in mbox_emails:
        if item['key'] in processed_keys:
            continue

        email_data = extract_email_data(item['msg'])
        if not email_data:
            continue

        email_date = parse_email_date(email_data['date'])
        if not email_date:
            print(f"DEBUG: Could not parse date for: {email_data['subject']}")
            continue

        print(f"DEBUG: Email '{email_data['subject'][:40]}' date: {email_date}")

        if email_date > cutoff_date:
            new_emails.append({
                "key": item['key'],
                "data": email_data,
                "date_obj": email_date
            })

    print(f"Found {len(new_emails)} new emails to process from the last {DAYS_BACK} days.")

    if not new_emails:
        return

    # Sort by date so oldest processes first = newest ends up at bottom of file
    new_emails.sort(key=lambda x: x['date_obj'])

    summary_header = f"# Email Summary - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    sus_header = f"# Suspicious Emails - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

    total = len(new_emails)
    for i, email_item in enumerate(new_emails):
        email_data = email_item['data']

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
            append_to_md(SUSPICIOUS_FILE, [entry], sus_header if i == 0 and not os.path.exists(SUSPICIOUS_FILE) else "")
            logging.warning(f"FLAGGED: {score}/10 - {email_data['subject'][:50]}")
            print(f"[{i + 1}/{total}] ⚠️ FLAGGED: {score}/10 - {email_data['subject']}")
        else:
            header = summary_header if i == 0 and not os.path.exists(SUMMARY_FILE) else ""
            append_to_md(SUMMARY_FILE, [entry], header)
            logging.info(f"CLEAN: {score}/10 - {email_data['subject'][:50]}")
            print(f"[{i + 1}/{total}] ✓ CLEAN: {score}/10 - {email_data['subject']}")

        processed.append({
            "key": email_item['key'],
            "subject": email_data['subject'],
            "date": email_data['date'],
            "processed_at": datetime.now().isoformat()
        })

    save_processed(processed)
    print(f"📂 Writing results complete. {total} emails processed.")
    print(f"💾 Cache updated. Total processed: {len(processed)}")

def delete_processed_emails():
    print("🗑️ Deleting processed emails from INBOX...")
    processed = load_processed()
    if not processed:
        print("No processed emails to delete.")
        return

    try:
        mbox = mailbox.mbox(THUNDERBIRD_INBOX)
        keys_to_delete = {p['key'] for p in processed}
        deleted_count = 0

        for key in keys_to_delete:
            try:
                del mbox[key]
                deleted_count += 1
            except KeyError:
                print(f"Warning: Key {key} not found in mbox")

        mbox.flush()
        mbox.close()

        os.remove(PROCESSED_FILE)
        print(f"✅ Deleted {deleted_count} emails from Thunderbird INBOX")
        print(f"✅ Removed {PROCESSED_FILE}")

    except Exception as e:
        logging.error(f"Failed to delete emails: {e}")
        print(f"Error deleting emails: {e}")

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--delete":
        delete_processed_emails()
    else:
        scan_recent_email()