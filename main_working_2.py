import os
import re
import json
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
    match = re.match(r'(.*)<(.*)>', full)
    if match:
        name = match.group(1).strip().strip('"')
        email = match.group(2).strip()
        return name, email
    else:
        return "", full.strip()

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
    except Exception:
        body = ""
    return body

# ---------------- Summarize email using Ollama ----------------
def summarize_text(text, model="mistral"):
    if not text.strip():
        return "(No content)"
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

# ---------------- Semantic Category using Ollama ----------------
def categorize_email(text, labels, model="mistral"):
    try:
        labels_str = ", ".join(labels) + ", Other"
        prompt = f"Categorize the following email into one of these labels: {labels_str}.\nEmail Content:\n{text}\nReturn only the label name."
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            capture_output=True,
            text=True
        )
        category = result.stdout.strip()
        if category not in labels:
            category = "Other"
        return category
    except Exception:
        return "Other"

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

# ---------------- Move Gmail to label ----------------
def move_to_label(service, msg_id, label_name):
    # Create label if not exists
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    label_id = None
    for lbl in labels:
        if lbl["name"].lower() == label_name.lower():
            label_id = lbl["id"]
            break
    if not label_id:
        label = service.users().labels().create(userId="me", body={"name": label_name}).execute()
        label_id = label["id"]
    # Apply label
    service.users().messages().modify(userId="me", id=msg_id, body={"addLabelIds": [label_id]}).execute()

# ---------------- Main Function ----------------
def fetch_and_process_emails():
    # Load config labels
    if os.path.exists("config.json"):
        with open("config.json", "r") as f:
            config = json.load(f)
        labels_list = config.get("Label", [])
    else:
        labels_list = []

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

        # Extract headers
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
        sender_full = next((h["value"] for h in headers if h["name"] == "From"), "(Unknown Sender)")
        sender_name, sender_email = parse_email(sender_full)
        to_full = next((h["value"] for h in headers if h["name"] == "To"), "")
        _, to_email = parse_email(to_full)

        # Body and forwarded check
        body = get_email_body(full_msg["payload"])
        forwarded = "Yes" if "Fwd:" in subject or "FW:" in subject else "No"

        # Check attachments
        attachment = "No"
        attachment_names = ""
        if "parts" in full_msg["payload"]:
            for part in full_msg["payload"]["parts"]:
                if part.get("filename"):
                    attachment = "Yes"
                    attachment_names += part.get("filename") + ", "

        attachment_names = attachment_names.rstrip(", ")

        # Section
        section = get_section(full_msg.get("labelIds", []))

        # Semantic Category
        category = categorize_email(subject + "\n" + body, labels_list)

        # Move email to respective label
        if category != "Other":
            move_to_label(service, msg["id"], category)

        # Time taken
        end_time = time.time()
        time_taken = round(end_time - start_time, 2)

        # Email date
        timestamp = int(full_msg["internalDate"])
        date = pd.to_datetime(timestamp, unit='ms')

        rows.append([
            sender_name, sender_email, to_email,
            forwarded, subject, body, section,
            attachment, attachment_names, date,
            time_taken, category
        ])

        # Mark as read
        service.users().messages().modify(
            userId="me",
            id=msg["id"],
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()

    # Append to CSV
    df_new = pd.DataFrame(rows, columns=[
        "From Name", "From Email", "To Email", "Forwarded", "Subject",
        "Body", "Section", "Attachment", "Attachment Names", "Date",
        "TimeTaken", "Category"
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
