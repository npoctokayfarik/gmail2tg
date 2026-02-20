from __future__ import annotations
from typing import List, Dict, Any
import base64
import re

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from bs4 import BeautifulSoup

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

TOKEN_FILE = "token.json"
CREDS_FILE = "credentials.json"


# 🔥 ЭТА ФУНКЦИЯ НУЖНА
def get_gmail_service():
    creds = None
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    except Exception:
        creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def list_unread(service, max_results: int = 10) -> List[Dict[str, str]]:
    res = service.users().messages().list(
        userId="me",
        q="in:inbox is:unread",
        maxResults=max_results
    ).execute()
    return res.get("messages", []) or []


def get_message(service, msg_id: str) -> Dict[str, Any]:
    return service.users().messages().get(
        userId="me",
        id=msg_id,
        format="full"
    ).execute()


def mark_as_read(service, msg_id: str) -> None:
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["UNREAD"]}
    ).execute()


def _header(payload: Dict[str, Any], name: str) -> str:
    for h in payload.get("headers", []) or []:
        if (h.get("name") or "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_b64url(data: str) -> str:
    if not data:
        return ""
    data = data.replace("-", "+").replace("_", "/")
    pad = "=" * ((4 - len(data) % 4) % 4)
    return base64.b64decode(data + pad).decode("utf-8", errors="replace")


def extract_text_plain_or_html(payload: Dict[str, Any]) -> str:
    plain_parts = []
    html_parts = []

    def walk(p: Dict[str, Any]):
        mt = p.get("mimeType")
        body = p.get("body", {}) or {}

        if mt == "text/plain" and body.get("data"):
            plain_parts.append(_decode_b64url(body["data"]))

        if mt == "text/html" and body.get("data"):
            html_parts.append(_decode_b64url(body["data"]))

        for part in (p.get("parts", []) or []):
            walk(part)

    walk(payload)

    plain_text = "\n".join(x.strip() for x in plain_parts if x.strip()).strip()
    if plain_text:
        return _cleanup_text(plain_text)

    html = "\n".join(x for x in html_parts if x).strip()
    if not html:
        return ""

    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text("\n")
    return _cleanup_text(text)


def _cleanup_text(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()


def format_for_telegram(msg: Dict[str, Any]) -> str:
    payload = msg.get("payload", {}) or {}

    from_ = _header(payload, "From")
    subject = _header(payload, "Subject")
    date = _header(payload, "Date")

    body_text = extract_text_plain_or_html(payload)

    if len(body_text) > 3500:
        body_text = body_text[:3500] + "\n…(cut)"

    gmail_link = f"https://mail.google.com/mail/u/0/#inbox/{msg.get('id')}"

    return (
        "📩 New Gmail\n"
        f"👤 From: {from_}\n"
        f"🧾 Subject: {subject}\n"
        f"🕒 Date: {date}\n\n"
        f"📝 {body_text if body_text else '(пусто)'}\n\n"
        f"🔗 {gmail_link}"
    )