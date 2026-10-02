"""First-time channel authorization. Run by an operator, not by the station timer."""

from youtube.auth import authorize, public_status
from youtube.api import client
from youtube.auth import channel_summary
from youtube.errors import AuthRequired


def main():
    try:
        creds = authorize()
        summary = channel_summary(client(creds))
    except AuthRequired as exc:
        print("YouTube authentication unavailable.")
        print("Operator authorization required.")
        print(str(exc)[:180])
        raise SystemExit(2)
    print(public_status(summary))


if __name__ == "__main__":
    main()
