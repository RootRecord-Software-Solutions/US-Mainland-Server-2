"""OAuth for the RootRecord YouTube channel. Tokens stay outside git."""

import json
import re
from pathlib import Path

from youtube.config import CONFIG_DIR
from youtube.errors import AuthRequired

SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
SECRET_MARK = re.compile(r"(ya29\.[A-Za-z0-9_\-]+|1//[A-Za-z0-9_\-]+)")


def redact(text):
    return SECRET_MARK.sub("[redacted]", str(text))[:240]


def secret_path():
    return CONFIG_DIR / "client_secret.json"


def token_path():
    return CONFIG_DIR / "token.json"


def _google():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    return Request, Credentials, InstalledAppFlow


def load_credentials():
    path = token_path()
    if not path.is_file():
        raise AuthRequired("YouTube authentication unavailable. Operator authorization required.")
    Request, Credentials, _flow = _google()
    creds = Credentials.from_authorized_user_file(str(path), [SCOPE])
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds)
        return creds
    raise AuthRequired("YouTube authentication unavailable. Operator authorization required.")


def save_credentials(creds):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = token_path()
    path.write_text(creds.to_json(), encoding="utf-8")
    path.chmod(0o640)


def authorize():
    """Operator step. Prints a URL. Does not open a browser by itself."""
    path = secret_path()
    if not path.is_file():
        raise AuthRequired("Missing client_secret.json in the protected YouTube directory.")
    _request, _creds, InstalledAppFlow = _google()
    flow = InstalledAppFlow.from_client_secrets_file(str(path), [SCOPE])
    creds = flow.run_local_server(
        host="localhost",
        port=8765,
        open_browser=False,
        prompt="consent",
        access_type="offline",
    )
    save_credentials(creds)
    return creds


def channel_summary(youtube):
    response = youtube.channels().list(part="id,snippet,status", mine=True).execute()
    items = response.get("items") or []
    if not items:
        raise AuthRequired("The token is valid and no channel was returned.")
    item = items[0]
    snippet = item.get("snippet") or {}
    return {
        "title": snippet.get("title") or "",
        "id": item.get("id") or "",
    }


def public_status(summary):
    return (
        "YouTube authentication: OK\n"
        f"Channel: {summary.get('title') or 'unknown'}\n"
        f"Channel ID: {summary.get('id') or 'unknown'}\n"
        "Live API access: OK"
    )


def main():
    try:
        authorize()
    except AuthRequired as exc:
        print("YouTube authentication unavailable.")
        print("Operator authorization required.")
        print(redact(exc))
        raise SystemExit(2)
    from youtube.api import client
    summary = channel_summary(client(load_credentials()))
    print(public_status(summary))


if __name__ == "__main__":
    main()
