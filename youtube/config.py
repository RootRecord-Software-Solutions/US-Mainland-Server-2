"""Station metadata. Secrets stay in /etc/rootrecord/youtube/."""

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HAWAII = ZoneInfo("Pacific/Honolulu")
CONFIG_DIR = Path(os.environ.get("YOUTUBE_CONFIG_DIR", "/etc/rootrecord/youtube"))
REPO_CONFIG = Path(__file__).resolve().parents[1] / "config" / "broadcast.yaml"

DEFAULTS = {
    "stream_title": "RootRecord Station",
    "title_template": "RootRecord Live — {date}",
    "description_template": "RootRecord live broadcast.\nrootrecord.cloud\n",
    "privacy_status": "public",
    "made_for_kids": False,
    "enable_dvr": True,
    "record_from_start": True,
    "resolution": "720p",
    "frame_rate": "30fps",
    "page_url": "https://www.rootrecord.cloud/live?broadcast=1",
}


def render_template(template, when=None):
    moment = when or datetime.now(HAWAII)
    local = moment.astimezone(HAWAII)
    return template.format(
        date=local.strftime("%Y-%m-%d"),
        time=local.strftime("%H:%M HST"),
    )


def _parse_simple_yaml(text):
    """Read the small broadcast.yaml shape without requiring PyYAML."""
    data = {}
    block = None
    for raw in text.splitlines():
        if raw.strip().startswith("#"):
            continue
        if block is not None and (raw.startswith("  ") or raw.strip() == ""):
            data[block] += (raw[2:] if raw.startswith("  ") else "") + "\n"
            if raw.strip() == "" and data[block].strip():
                continue
            continue
        block = None
        if ":" not in raw or raw.startswith(" "):
            continue
        name, value = raw.split(":", 1)
        name = name.strip()
        value = value.strip().strip('"')
        if value == "|":
            block = name
            data[name] = ""
            continue
        if value in ("true", "false"):
            data[name] = value == "true"
        else:
            data[name] = value
    return data


def load_settings():
    settings = dict(DEFAULTS)
    if REPO_CONFIG.is_file():
        parsed = _parse_simple_yaml(REPO_CONFIG.read_text(encoding="utf-8"))
        settings.update({k: v for k, v in parsed.items() if k in DEFAULTS or True})
    return settings
