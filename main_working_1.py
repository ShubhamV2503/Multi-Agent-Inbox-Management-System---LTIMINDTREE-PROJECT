import os
import re
import base64
import subprocess
import time
import pandas as pd
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ---------------- Gmail API scope ----------------
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# ---------------- Gmail Authentication ----------------
def gmail_authenticate():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

# ---------------- Helper: Parse email ----------------
def parse_email(full):
    try:
        match = re.match(r'(.*)<(.*)>', full)
        if match:
            email = match.group(2).strip()
            return email
        else:
            return full.strip()
    except:
        return full.strip()

# ---------------- Extract email body ----------------
def get_email_body(payload):
    body = ""
    try:
        if "data" in payload.get("body", {}):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
        elif "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain" and "data" in part["body"]:
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                    break
        # Remove repeated forwarded headers
        body = re.sub(r'(-----? Forwarded message -----?.*?\n)+', '', body, flags=re.DOTALL|re.IGNORECASE)
    except:
        body = "(Could not extract body)"
    return body

# ---------------- Summarize email using Ollama ----------------
def summarize_text(text, model="mistral"):
    if not text.strip():
        return "(No content to summarize)"
    try:
        prompt = f"Summarize this email in 2-3 sentences:\n\n{text}"
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
    except Exception as e:
        return f"(Summary failed: {str(e)})"

# ---------------- Detect Gmail Section ----------------
def get_section(label_ids):
    if "CATEGORY_SOCIAL" in label_ids:
        return "Social"
    elif "CATEGORY_PROMOTIONS" in label_ids:
        return "Promotions"
    elif "CATEGORY_UPDATES" in label_ids:
        return "Updates"
    elif "CATEGORY_FORUMS" in label_ids:
        return "Forums"
    else:
        return "Primary"

# ---------------- Main Function ----------------
def fetch_and_process_emails():
    service = gmail_authenticate()
    results = service.users().messages().list(userId="me", labelIds=["UNREAD"], maxResults=10).execute()
    messages = results.get("messages", [])

    if not messages:
        return "✅ No unread emails found."

    rows = []
    for msg in messages:
        start_time = time.time()
        full_msg = service.users().messages().get(userId="me", id=msg["id"]).execute()
        headers = full_msg["payload"]["headers"]

        # Extract headers with error handling
        def get_header(name):
            try:
                return next((h["value"] for h in headers if h["name"] == name), "")
            except:
                return ""

        subject = get_header("Subject") or "(No Subject)"
        sender_name = re.sub(r'<.*?>', '', get_header("From")).strip()
        sender_email = parse_email(get_header("From"))
        to_email = parse_email(get_header("To"))
        cc_email = parse_email(get_header("Cc"))
        bcc_email = parse_email(get_header("Bcc"))

        # Body and forwarded check
        body = get_email_body(full_msg["payload"])
        forwarded = "Yes" if re.search(r'\b(Fwd|FW):', subject, re.IGNORECASE) else "No"

        # Check attachments
        attachment = "No"
        attachment_names = ""
        if "parts" in full_msg["payload"]:
            for part in full_msg["payload"]["parts"]:
                if part.get("filename"):
                    attachment = "Yes"
                    attachment_names += part["filename"] + ", "
        attachment_names = attachment_names.rstrip(", ")

        # Section
        section = get_section(full_msg.get("labelIds", []))

        # Summarize body
        summary = summarize_text(body)

        # Time taken
        end_time = time.time()
        time_taken = round(end_time - start_time, 2)

        # Email date
        timestamp = int(full_msg["internalDate"])
        date = pd.to_datetime(timestamp, unit='ms')

        rows.append([
            sender_name, sender_email, to_email,
            cc_email, bcc_email,
            forwarded, subject, body, summary, attachment,
            attachment_names, section, date, time_taken
        ])

        # Mark as read
        service.users().messages().modify(
            userId="me",
            id=msg["id"],
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()

    # Append to CSV
    df_new = pd.DataFrame(rows, columns=[
        "From Name", "From Email", "To Email",
        "CC Email", "BCC Email",
        "Forwarded", "Subject", "Body", "Summary", "Attachment",
        "AttachmentNames", "Section", "Date", "TimeTaken"
    ])
    if os.path.exists("emails.csv"):
        df_existing = pd.read_csv("emails.csv")
        df_final = pd.concat([df_existing, df_new], ignore_index=True)
    else:
        df_final = df_new

    df_final.to_csv("emails.csv", index=False)
    return f"📩 Processed {len(rows)} emails and saved to emails.csv"

# ---------------- Main Script ----------------
if __name__ == "__main__":
    print(fetch_and_process_emails())
