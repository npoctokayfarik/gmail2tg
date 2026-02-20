import os
import base64
import re

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from bs4 import BeautifulSoup


# ====== CONFIG ======
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

# Railway Volume path (если есть)
DATA_DIR = os.getenv("DATA_DIR", "/app/data")

# Если volume не подключен/путь не существует — падаем назад на текущую папку
if not os.path.isdir(DATA_DIR):
    DATA_DIR = "."

TOKEN_FILE = os.path.join(DATA_DIR, "token.json")
CREDS_FILE = os.path.join(DATA_DIR, "credentials.json")
# =====================


def _ensure_dir():
    # На всякий случай (если DATA_DIR существует)
    try:
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    except Exception:
        pass


def write_file_from_env(path: str, env_name: str) -> None:
    """
    Для deploy: создаём credentials/token из env, если файла ещё нет.
    token.json будет лежать в Volume и сохранится между рестартами.
    """
    content = os.getenv(env_name)
    if not content:
        return
    if os.path.exists(path):
        return
    _ensure_dir()
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def get_gmail_service():
    # 1) подтягиваем файлы из env при первом запуске (если надо)
    write_file_from_env(CREDS_FILE, "GOOGLE_CREDENTIALS_JSON")
    write_file_from_env(TOKEN_FILE, "GOOGLE_TOKEN_JSON")

    creds = None
    try:
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    except Exception:
        creds = None

    # 2) если токен невалидный — обновляем/создаём
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_FILE):
                raise RuntimeError(
                    f"credentials.json not found at {CREDS_FILE}. "
                    f"Set GOOGLE_CREDENTIALS_JSON variable in Railway."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        _ensure_dir()
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def list_unread(service, max_results=10):
    res = service.users().messages().list(
        userId="me",
        q="in:inbox is:unread",
        maxResults=max_results
    ).execute()
    return res.get("messages", []) or []


def get_message(service, msg_id):
    return service.users().messages().get(
        userId="me",
        id=msg_id,
        format="full"
    ).execute()


def mark_as_read(service, msg_id):
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["UNREAD"]}
    ).execute()


def _header(payload, name):
    for h in payload.get("headers", []) or []:
        if (h.get("name") or "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_b64url(data):
    if not data:
        return ""
    data = data.replace("-", "+").replace("_", "/")
    pad = "=" * ((4 - len(data) % 4) % 4)
    return base64.b64decode(data + pad).decode("utf-8", errors="replace")


def extract_text(payload):
    """
    Достаём нормальный текст:
    - сначала text/plain
    - если нет — text/html -> чистим в текст
    """
    if not payload:
        return ""

    plain_parts = []
    html_parts = []

    def walk(p):
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
        return _cleanup(plain_text)

    html = "\n".join(x for x in html_parts if x).strip()
    if not html:
        return ""

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text("\n")
    return _cleanup(text)


def _cleanup(text):
    text = text.replace("\r", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()


def format_for_telegram(msg):
    payload = msg.get("payload", {}) or {}
    from_ = _header(payload, "From")
    subject = _header(payload, "Subject")
    date = _header(payload, "Date")

    body_text = extract_text(payload)
    if len(body_text) > 3500:
        body_text = body_text[:3500] + "\n…(cut)"

    gmail_link = f"https://mail.google.com/mail/u/0/#inbox/{msg.get('id')}"

    return (
        f"📩 New Gmail\n"
        f"👤 From: {from_}\n"
        f"🧾 Subject: {subject}\n"
        f"🕒 Date: {date}\n\n"
        f"📝 {body_text if body_text else '(пусто)'}\n\n"
        f"🔗 {gmail_link}"
    )