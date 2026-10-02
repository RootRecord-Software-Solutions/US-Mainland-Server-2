"""Confirm the saved token belongs to the RootRecord channel."""

from youtube.api import client
from youtube.auth import channel_summary, load_credentials, public_status, redact
from youtube.errors import AuthRequired, BroadcastError


def main():
    try:
        summary = channel_summary(client(load_credentials()))
    except AuthRequired as exc:
        print("YouTube authentication unavailable.")
        print("Operator authorization required.")
        print(redact(exc))
        raise SystemExit(2)
    except BroadcastError as exc:
        print(redact(exc))
        raise SystemExit(1)
    print(public_status(summary))


if __name__ == "__main__":
    main()
