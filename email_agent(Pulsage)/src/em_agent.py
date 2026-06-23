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

# === BASE PATHS ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# === CONFIG ===
THUNDERBIRD_INBOX = os.path.expanduser(r"C:\Users\Admin\AppData\Roaming\Thunderbird\Profiles\7you0l9t.default-release\ImapMail\imap.gmail.com\INBOX")
PROCESSED_FILE = os.path.join(BASE_DIR, "processed_emails.json")
SUMMARY_FILE = os.path.join(BASE_DIR, "summary.md")
SUSPICIOUS_FILE = os.path.join(BASE_DIR, "suspicious.md")
LOG_FILE = os.path.join(BASE_DIR, "email_agent.log")
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:1b"
DAYS_BACK = 3
CACHE_RETENTION_DAYS = DAYS_BACK + 2
SCAN_PROGRESS_EVERY = 1000
MAX_BODY_CHARS = 4000
OLLAMA_BODY_CHARS = 2500
OLLAMA_TIMEOUT = 120
OLLAMA_RETRIES = 2

# === LOGGING ===
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)


def log_run_start(processed_count):
    logging.info("=" * 72)
    logging.info(f"RUN START | model={MODEL} | days_back={DAYS_BACK} | cache_loaded={processed_count}")


def log_run_end(total, skipped_llm, parsed_dates, failed_dates, skipped_cache, summary_count, suspicious_count, runtime_sec):
    logging.info(
        "RUN END | processed=%s | skipped_llm=%s | parsed_dates=%s | failed_dates=%s | skipped_cache=%s | summary_entries=%s | suspicious_entries=%s | runtime_sec=%.2f",
        total,
        skipped_llm,
        parsed_dates,
        failed_dates,
        skipped_cache,
        summary_count,
        suspicious_count,
        runtime_sec,
    )


# === TIME HELPERS ===
def get_local_tzinfo():
    return datetime.now().astimezone().tzinfo


def format_display_date(date_str):
    dt = parse_email_date(date_str)
    if not dt:
        return date_str

    local_dt = dt.astimezone(get_local_tzinfo())
    return local_dt.strftime('%Y-%m-%d %I:%M %p %Z')


# === CORE HELPERS ===
def parse_email_date(date_str):
    if not date_str:
        return None

    # Standard RFC email format
    try:
        dt = parsedate_to_datetime(date_str)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=get_local_tzinfo())
            return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Thunderbird local mailbox formats
    thunderbird_formats = [
        "%Y.%m.%d-%H.%M.%S",
        "%Y.%m.%d.%H.%M",
    ]

    for fmt in thunderbird_formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            dt = dt.replace(tzinfo=get_local_tzinfo())
            return dt.astimezone(timezone.utc)
        except Exception:
            pass

    # Fallback parser
    try:
        dt = parser.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=get_local_tzinfo())
        return dt.astimezone(timezone.utc)
    except Exception:
        logging.warning(f"Unable to parse date: {date_str}")
        return None


def make_email_id(email_data):
    message_id = (email_data.get('message_id') or '').strip()
    if message_id:
        return hashlib.md5(message_id.encode('utf-8')).hexdigest()

    unique_str = f"{email_data['subject']}|{email_data['date']}|{email_data['from']}"
    return hashlib.md5(unique_str.encode('utf-8')).hexdigest()


def sort_processed(processed_list):
    def sort_key(item):
        processed_at = item.get('processed_at') if isinstance(item, dict) else None
        if not processed_at:
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            dt = datetime.fromisoformat(processed_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    return sorted(
        [item for item in processed_list if isinstance(item, dict) and item.get('id')],
        key=sort_key,
        reverse=True
    )


def prune_processed(processed_list):
    if not processed_list:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_RETENTION_DAYS)
    pruned = []

    for item in processed_list:
        if not isinstance(item, dict):
            continue

        processed_at = item.get('processed_at')
        if not processed_at:
            continue

        try:
            dt = datetime.fromisoformat(processed_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)

            if dt >= cutoff:
                pruned.append(item)
        except Exception:
            pruned.append(item)

    return sort_processed(pruned)


def load_processed():
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            return prune_processed(data)
        except json.JSONDecodeError:
            logging.warning("Processed cache JSON invalid. Starting fresh.")
            return []
        except Exception as e:
            logging.error(f"Failed to load processed cache: {e}")
            return []
    return []


def save_processed(processed_list):
    processed_list = prune_processed(processed_list)
    temp_path = PROCESSED_FILE + '.tmp'
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(processed_list, f, indent=2)
    os.replace(temp_path, PROCESSED_FILE)


def load_mbox_emails():
    try:
        print(f"Loading emails from: {THUNDERBIRD_INBOX}")
        print("Scanning mailbox... this can take a bit on large inboxes.")

        if not os.path.exists(THUNDERBIRD_INBOX):
            print(f"ERROR: INBOX file not found at {THUNDERBIRD_INBOX}")
            return []

        mbox = mailbox.mbox(THUNDERBIRD_INBOX)
        emails = []

        for idx, (key, msg) in enumerate(mbox.items(), start=1):
            emails.append({"key": key, "msg": msg})
            if idx % SCAN_PROGRESS_EVERY == 0:
                print(f"Scanned {idx} emails...")

        print(f"Loaded {len(emails)} total emails from mbox")
        return emails
    except Exception as e:
        logging.error(f"Failed to load mbox: {e}")
        print(f"ERROR: Failed to load mbox: {e}")
        return []


def decode_payload(payload, preferred_charset=None):
    if not payload:
        return ""

    for encoding in [preferred_charset, 'utf-8', 'latin-1', 'cp1252']:
        if not encoding:
            continue
        try:
            return payload.decode(encoding, errors='ignore')
        except Exception:
            continue

    return ""


def extract_email_data(msg):
    try:
        subject = str(make_header(decode_header(msg['Subject'] or "(No Subject)")))
        from_addr = str(make_header(decode_header(msg['From'] or "(Unknown Sender)")))
        date_str = msg['Date'] or ""
        message_id = msg.get('Message-ID', '') or msg.get('Message-Id', '') or ""

        body = ""
        html_fallback = ""

        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue

                disposition = (part.get('Content-Disposition') or '').lower()
                if disposition.startswith('attachment'):
                    continue

                content_type = part.get_content_type()
                payload = part.get_payload(decode=True)
                text = decode_payload(payload, part.get_content_charset())

                if not text:
                    continue

                if content_type == 'text/plain' and not body:
                    body = text
                elif content_type == 'text/html' and not html_fallback:
                    html_fallback = text
        else:
            payload = msg.get_payload(decode=True)
            text = decode_payload(payload, msg.get_content_charset())
            if msg.get_content_type() == 'text/plain':
                body = text
            else:
                html_fallback = text

        if not body and html_fallback:
            body = html_fallback

        body = body.replace('\r\n', '\n').replace('\r', '\n').strip()

        if len(body) > MAX_BODY_CHARS:
            body = body[:2000] + "\n...\n" + body[-2000:]

        return {
            "subject": subject.strip(),
            "from": from_addr.strip(),
            "date": date_str.strip(),
            "display_date": format_display_date(date_str.strip()),
            "message_id": message_id.strip(),
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

    if not reasons:
        reasons.append("No rule hits")

    return min(score, 10), reasons


def should_skip_llm(email_data):
    subject = email_data["subject"].lower()
    body = email_data["body"]
    sender = email_data["from"].lower()

    if len(body.strip()) < 50:
        return True, "Very little text content"

    link_count = body.count("http")
    if link_count > 10:
        return True, "Link-heavy marketing email"

    wallpaper_keywords = [
        "wallpaper",
        "one piece",
        "anime wallpaper"
    ]
    if any(k in subject for k in wallpaper_keywords):
        return True, "Wallpaper email"

    promo_keywords = [
        "new arrivals",
        "shop now",
        "limited time",
        "sale",
        "collection"
    ]
    if any(k in subject for k in promo_keywords):
        return True, "Promotional email"

    if "pinterest" in sender:
        return True, "Pinterest"

    if "bestbuy" in sender:
        return True, "Retail promotion"

    return False, None


def query_gemma(email_data, session=None):
    trimmed_body = email_data['body'][:OLLAMA_BODY_CHARS]

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

Action Required: <comma-separated list of required actions, or \"None\">
Deadline: <explicit date/time IF present; otherwise \"None\">
Priority: <High, Medium, Low>

Rules:
- Use the email date only to understand relative time words like today, tomorrow, this week, or next week.
- Do not calculate future dates unless they are explicitly stated.
- If there is no clear deadline, write \"None\".
- If the email does not require the user to do anything, write \"None\" for Action Required.
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
Body: {trimmed_body}
"""

    requester = session or requests
    start1 = time.time()

    try:
        for attempt in range(1, OLLAMA_RETRIES + 1):
            try:
                response = requester.post(OLLAMA_URL, json={
                    "model": MODEL,
                    "prompt": message,
                    "stream": False
                }, timeout=OLLAMA_TIMEOUT)

                response.raise_for_status()
                result = response.json().get('response', '').strip()
                if result:
                    return result

                logging.warning("Ollama returned an empty response")
            except Exception as e:
                logging.error(f"Gemma query failed on attempt {attempt}: {e}")
                if attempt == OLLAMA_RETRIES:
                    return "Could not generate summary - connection failed"

        return "Could not generate summary - empty response"
    finally:
        end1 = time.time()
        print(f"Gemma Time: {end1 - start1:.2f}s")


def prepend_to_md(filepath, entries, header=""):
    """Prepends the newest batch on top, preserving older batches below it."""
    print(f"Writing {len(entries)} entries to {filepath}")
    directory = os.path.dirname(filepath)

    if directory:
        os.makedirs(directory, exist_ok=True)

    existing_content = ""
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            existing_content = f.read().strip()

    with open(filepath, 'w', encoding='utf-8') as f:
        if header:
            f.write(header)

        for e in entries:
            f.write(f"### {e['score']}/10 - {e['subject']}\n\n")
            f.write(f"**From:** `{e['from']}`  \n")
            f.write(f"**Date:** {e['display_date']}  \n")
            f.write(f"**Reasons:** {', '.join(e['reasons']) if e['reasons'] else 'No rule hits'}  \n")
            f.write(f"**Summary:** {e['verdict']}\n\n")

        if existing_content:
            f.write("\n\n---\n## Previous Batches\n\n")
            f.write(existing_content)


def scan_recent_email():
    skipped_llm = 0
    parsed_dates = 0
    failed_dates = 0

    start_time = time.time()
    print(f"Starting email scan, using Model: {MODEL}")
    processed = load_processed()
    processed_ids = {p['id'] for p in processed if isinstance(p, dict) and 'id' in p}
    print(f"Already processed {len(processed_ids)} emails before")
    log_run_start(len(processed_ids))

    mbox_emails = load_mbox_emails()
    if not mbox_emails:
        print("No emails found. Check Thunderbird path and make sure Thunderbird is closed.")
        logging.warning("RUN ABORTED | No emails found or mailbox unavailable")
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

    new_emails.sort(key=lambda x: x['date_obj'], reverse=True)
    run_stamp = datetime.now().astimezone(get_local_tzinfo()).strftime('%Y-%m-%d %I:%M %p %Z')
    summary_header = f"## Email Summary - {run_stamp}\n\n"
    suspicious_header = f"## Suspicious Email Report - {run_stamp}\n\n"

    total = len(new_emails)
    suspicious_entries = []
    summary_entries = []
    session = requests.Session()

    for i, email_item in enumerate(new_emails):
        email_start = time.time()
        email_data = email_item["data"]

        print(f"\nProcessing {i + 1}/{total}: {email_data['subject'][:60]}")

        score, reasons = score_email(email_data)
        print(f"Body Length: {len(email_data['body'])}")

        skip, reason = should_skip_llm(email_data)
        if skip:
            verdict = f"Skipped LLM - {reason}"
            skipped_llm += 1
            print(f"LLM Skipped: {reason}")
        else:
            verdict = query_gemma(email_data, session=session)

        entry = {
            "score": score,
            "subject": email_data["subject"],
            "from": email_data["from"],
            "date": email_data["date"],
            "display_date": email_data["display_date"],
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

        processed.append({
            "id": email_item["id"],
            "subject": email_data["subject"],
            "date": email_data["date"],
            "processed_at": datetime.now(timezone.utc).isoformat()
        })

        print(f"Time: {time.time() - email_start:.2f}s")

    print(f"Summary Entries: {len(summary_entries)}")
    print(f"Suspicious Entries: {len(suspicious_entries)}")
    save_processed(processed)

    if summary_entries:
        prepend_to_md(SUMMARY_FILE, summary_entries, summary_header)
    if suspicious_entries:
        prepend_to_md(SUSPICIOUS_FILE, suspicious_entries, suspicious_header)

    end_time = time.time()
    runtime_sec = end_time - start_time
    log_run_end(
        total=total,
        skipped_llm=skipped_llm,
        parsed_dates=parsed_dates,
        failed_dates=failed_dates,
        skipped_cache=skipped,
        summary_count=len(summary_entries),
        suspicious_count=len(suspicious_entries),
        runtime_sec=runtime_sec,
    )

    print(f"\n📂 Done!, took ⏱ {runtime_sec:.2f} secs and {total} emails processed.")
    print(f"🤖 LLM Calls Skipped: {skipped_llm}")
    print(f"💾 Total in cache: {len(prune_processed(processed))}")
    print(f"📝 Check {SUMMARY_FILE} and {SUSPICIOUS_FILE}")


if __name__ == "__main__":
    scan_recent_email()
