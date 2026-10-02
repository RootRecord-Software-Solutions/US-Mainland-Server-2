"""One reusable liveStream, one broadcast per station start."""

import time
from datetime import datetime, timedelta

from youtube import api
from youtube.auth import channel_summary, load_credentials, public_status
from youtube.config import CONFIG_DIR, HAWAII, load_settings, render_template
from youtube.errors import AuthRequired, BroadcastError


class LiveSession:
    def __init__(self, log):
        self.log = log
        self.settings = load_settings()
        self.youtube = None
        self.broadcast_id = ""
        self.stream_id = ""
        self.ingest_address = ""
        self.stream_name = ""
        self.live = False

    def prepare(self):
        creds = load_credentials()
        self.youtube = api.client(creds)
        summary = channel_summary(self.youtube)
        self.log("YOUTUBE AUTH", channel=summary.get("id") or "ok")
        print(public_status(summary), flush=True)
        stream = self._reusable_stream()
        self.stream_id = stream.get("id") or ""
        ingestion = ((stream.get("cdn") or {}).get("ingestionInfo") or {})
        self.ingest_address = ingestion.get("ingestionAddress") or ""
        self.stream_name = ingestion.get("streamName") or ""
        if not self.stream_id or not self.ingest_address or not self.stream_name:
            raise BroadcastError("The reusable stream has no ingest configuration.")
        self._remember_stream_id()
        broadcast = self._create_broadcast()
        self.broadcast_id = broadcast.get("id") or ""
        bound = api.bind_broadcast(self.youtube, self.broadcast_id, self.stream_id)
        bound_stream = ((bound.get("contentDetails") or {}).get("boundStreamId") or "")
        if bound_stream != self.stream_id:
            raise BroadcastError("Broadcast binding failed.")
        self.log("BROADCAST READY", broadcast=self.broadcast_id, stream=self.stream_id)
        return self.ingest_address, self.stream_name

    def destination(self):
        from urllib.parse import urlparse
        path = urlparse(self.ingest_address).path or "/live2"
        if not path.endswith("/"):
            path += "/"
        return f"rtmps://a.rtmps.youtube.com:443{path}{self.stream_name}"

    def go_live(self, timeout=150):
        deadline = time.monotonic() + timeout
        delay = 2
        while time.monotonic() < deadline:
            listed = api.get_stream(self.youtube, self.stream_id)
            items = listed.get("items") or []
            if items and api.stream_is_active(items[0]):
                self._transition("testing")
                self._transition("live")
                self.live = True
                self.log("BROADCAST LIVE", broadcast=self.broadcast_id)
                return
            time.sleep(delay)
            delay = min(delay + 2, 10)
        raise BroadcastError("The bound stream did not become active.")

    def finish(self):
        if not self.youtube or not self.broadcast_id:
            return
        try:
            if self.live:
                self._transition("complete")
                self.log("BROADCAST END", broadcast=self.broadcast_id)
            else:
                api.delete_broadcast(self.youtube, self.broadcast_id)
                self.log("BROADCAST END", broadcast=self.broadcast_id, removed="yes")
        except (AuthRequired, BroadcastError) as exc:
            self.log("BROADCAST END", detail=str(exc)[:180])
        self.live = False

    def _reusable_stream(self):
        saved = self._saved_stream_id()
        if saved:
            listed = api.get_stream(self.youtube, saved)
            items = listed.get("items") or []
            if items:
                return items[0]
        title = self.settings["stream_title"]
        listed = api.list_streams(self.youtube)
        for item in listed.get("items") or []:
            if ((item.get("snippet") or {}).get("title") == title):
                return item
        return api.create_stream(
            self.youtube,
            title,
            self.settings["resolution"],
            self.settings["frame_rate"],
        )

    def _create_broadcast(self):
        when = datetime.now(HAWAII)
        start = when.strftime("%Y-%m-%dT%H:%M:%S%z")
        # YouTube wants a colon in the offset.
        if len(start) > 5 and start[-5] in "+-":
            start = start[:-2] + ":" + start[-2:]
        end = (when + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S%z")
        if len(end) > 5 and end[-5] in "+-":
            end = end[:-2] + ":" + end[-2:]
        body = {
            "snippet": {
                "title": render_template(self.settings["title_template"], when),
                "description": render_template(self.settings["description_template"], when).strip(),
                "scheduledStartTime": start,
                "scheduledEndTime": end,
            },
            "status": {
                "privacyStatus": self.settings["privacy_status"],
                "selfDeclaredMadeForKids": bool(self.settings["made_for_kids"]),
            },
            "contentDetails": {
                "enableDvr": bool(self.settings["enable_dvr"]),
                "recordFromStart": bool(self.settings["record_from_start"]),
                "enableAutoStart": False,
                "enableAutoStop": False,
            },
        }
        return api.create_broadcast(self.youtube, body)

    def _transition(self, status):
        try:
            api.transition_broadcast(self.youtube, self.broadcast_id, status)
        except BroadcastError:
            if status != "testing":
                raise

    def _saved_stream_id(self):
        path = CONFIG_DIR / "stream_id"
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def _remember_stream_id(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        path = CONFIG_DIR / "stream_id"
        path.write_text(self.stream_id + "\n", encoding="utf-8")
        path.chmod(0o640)
