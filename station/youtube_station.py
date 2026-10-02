#!/usr/bin/env python3
"""Start and watch one FFmpeg process for the YouTube station.

Python chooses the program. FFmpeg sends the picture, the sound, and RTMPS.
The stream key is read from the environment, never from this repository.
"""

import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from program import Program

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
HAWAII = ZoneInfo("Pacific/Honolulu")
VIDEO_BITRATE = "800k"
VIDEO_MAXRATE = "1000k"
AUDIO_BITRATE = "128k"


def log(event, **fields):
    def clean(value):
        return re.sub(r"rtmps?://\S+", "rtmps://[redacted]", str(value))
    extra = " ".join(f"{key}={clean(value)}" for key, value in fields.items())
    line = event if not extra else f"{event} {extra}"
    print(line, flush=True)


def env_int(name):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return 0
    return int(raw)


class Station:
    def __init__(self):
        self.stopping = False
        self.mode = os.environ.get("STATION_MODE", "slate").strip() or "slate"
        self.root = Path(os.environ.get("STATION_ROOT", "/var/lib/rootrecord/station"))
        self.url = os.environ.get("YOUTUBE_URL", "rtmps://a.rtmps.youtube.com:443/live2").rstrip("/")
        self.key = os.environ.get("YOUTUBE_KEY", "").strip()
        self.sink = os.environ.get("STATION_SINK", "rtmps").strip() or "rtmps"
        self.visual = os.environ.get("STATION_VISUAL", "generated").strip() or "generated"
        self.max_seconds = env_int("STATION_MAX_SECONDS")
        self.state = self.root / "state"
        self.slate = self.state / "slate.txt"
        self.progress = self.state / "ffmpeg-progress.txt"
        self.proc = None
        self.program = None
        self.session = None
        self.capture = None
        self.live_started = False
        self.started = time.monotonic()
        self.connected = False

    def stop(self, *_args):
        self.stopping = True
        self._end_ffmpeg()

    def _destination(self):
        if self.sink == "file":
            return str(self.state / "preview.mkv")
        if self.session is not None:
            return self.session.destination()
        if not self.key:
            log("STATION STOP", reason="missing_youtube_key")
            raise SystemExit(2)
        return f"{self.url}/{self.key}"

    def _write_slate(self, title):
        self.state.mkdir(parents=True, exist_ok=True)
        clock = datetime.now(HAWAII).strftime("%H:%M HST")
        text = (title or "Standing by").replace("\n", " ").strip()
        body = "\n".join(["ROOTRECORD", text, clock, "rootrecord.cloud"])
        self.slate.write_text(body + "\n", encoding="utf-8")

    def _filters(self):
        return (
            "drawtext=fontfile=%s:textfile=%s:reload=1:fontsize=42:"
            "fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2"
            % (FONT, self.slate)
        )

    def _command(self, dest):
        if self.visual == "page" and self.capture is not None:
            sources = self.capture.ffmpeg_inputs()
            filters = ["-map", "0:v:0", "-map", "1:a:0"]
        else:
            sources = ["-re", "-f", "lavfi", "-i", "color=c=0x0e1a14:s=1280x720:r=15"]
            if self.mode == "program":
                sources += ["-f", "s16le", "-ar", "48000", "-ac", "2", "-i", "pipe:0"]
            else:
                sources += ["-re", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
            filters = ["-vf", self._filters()]
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning",
            *sources,
            *filters,
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
            "-b:v", VIDEO_BITRATE, "-maxrate", VIDEO_MAXRATE, "-bufsize", "1600k",
            "-pix_fmt", "yuv420p", "-r", "15", "-g", "30",
            "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "48000",
            "-progress", str(self.progress), "-nostats",
        ]
        if self.max_seconds:
            cmd += ["-t", str(self.max_seconds)]
        if self.sink == "rtmps":
            cmd += ["-f", "flv", "-flvflags", "no_duration_filesize", dest]
        else:
            cmd += ["-y", dest]
        return cmd

    def _end_ffmpeg(self):
        if self.proc is None or self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=3)

    def _read_progress(self):
        if not self.progress.is_file():
            return {}
        fields = {}
        for line in self.progress.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]:
            if "=" in line:
                key, value = line.split("=", 1)
                fields[key] = value.strip()
        return fields

    def _watch_progress(self):
        fields = self._read_progress()
        bitrate = fields.get("bitrate", "")
        fps = fields.get("fps", "")
        if bitrate or fps:
            log("BITRATE", value=bitrate or "0")
            log("FPS", value=fps or "0")
        alive = self.proc is not None and self.proc.poll() is None
        log("ENCODER HEALTH", value="running" if alive else "down")
        log("RTMPS HEALTH", value="up" if alive and self.sink == "rtmps" else "down" if self.sink == "rtmps" else "local")
        if self.sink == "rtmps" and alive and not self.connected and (time.monotonic() - self.born) > 5:
            self.connected = True
            log("YOUTUBE CONNECTION ESTABLISHED")

    def _run_once(self, dest):
        title = "Station test" if self.mode == "slate" else "Standing by"
        self._write_slate(title)
        log("PROGRAM", value=title)
        self.progress.write_text("", encoding="utf-8")
        cmd = self._command(dest)
        log("FFMPEG START", mode=self.mode, sink=self.sink, visual=self.visual, video=VIDEO_MAXRATE, audio=AUDIO_BITRATE)
        pipe_program = self.mode == "program" and self.visual != "page"
        stdin = subprocess.PIPE if pipe_program else subprocess.DEVNULL
        self.proc = subprocess.Popen(cmd, stdin=stdin, stderr=subprocess.PIPE)
        self.born = time.monotonic()
        self.connected = False
        if self.session is not None and not self.live_started:
            self.live_started = True
            threading.Thread(target=self._go_live, daemon=True).start()
        next_log = time.monotonic() + 5
        try:
            while not self.stopping:
                if self.max_seconds and (time.monotonic() - self.started) >= self.max_seconds:
                    self.stopping = True
                    break
                if self.proc.poll() is not None:
                    break
                if pipe_program:
                    frame, title = self.program.read_frame()
                    if title:
                        self._write_slate(title)
                    try:
                        self.proc.stdin.write(frame)
                    except BrokenPipeError:
                        break
                if time.monotonic() >= next_log:
                    self._watch_progress()
                    if pipe_program:
                        log("PROGRAM", value=self.program.title)
                    next_log = time.monotonic() + 5
                if not pipe_program:
                    self._write_slate("Station test")
                    time.sleep(0.2)
        finally:
            if self.proc.stdin:
                try:
                    self.proc.stdin.close()
                except Exception:
                    pass
            self._end_ffmpeg()
            err = b""
            if self.proc.stderr:
                err = self.proc.stderr.read() or b""
            text = err.decode(errors="replace").strip()
            if text:
                log("FFMPEG", detail=text[-300:].replace("\n", " "))
        code = self.proc.returncode
        if self.max_seconds and (time.monotonic() - self.started) >= self.max_seconds:
            self.stopping = True
        return code

    def _go_live(self):
        from youtube.errors import AuthRequired, BroadcastError
        try:
            self.session.go_live()
        except AuthRequired:
            log("BROADCAST", detail="authentication unavailable")
        except BroadcastError as exc:
            log("BROADCAST", detail=str(exc)[:180])

    def _prepare(self):
        token = Path("/etc/rootrecord/youtube/token.json")
        enabled = os.environ.get("YOUTUBE_API", "") == "1" or token.is_file()
        if not enabled:
            return
        root = Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from youtube.broadcast import LiveSession
        from youtube.errors import AuthRequired, BroadcastError
        self.session = LiveSession(log)
        try:
            self.session.prepare()
        except AuthRequired:
            log("STATION STOP", reason="youtube_auth")
            print("YouTube authentication unavailable.", flush=True)
            print("Operator authorization required.", flush=True)
            raise SystemExit(2)
        except BroadcastError as exc:
            log("STATION STOP", reason="broadcast", detail=str(exc)[:180])
            raise SystemExit(1)

    def _open_page(self):
        if self.visual != "page":
            return
        root = Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from page_capture import PageCapture
        from youtube.config import load_settings
        self.capture = PageCapture(load_settings()["page_url"])
        try:
            self.capture.start()
        except RuntimeError as exc:
            log("STATION STOP", reason="page_capture", detail=str(exc)[:180])
            raise SystemExit(1)

    def run(self):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        self.state.mkdir(parents=True, exist_ok=True)
        if self.mode == "program":
            self.program = Program(self.root)
        log("STATION START", mode=self.mode, sink=self.sink, visual=self.visual)
        self._prepare()
        self._open_page()
        try:
            dest = self._destination()
        except SystemExit:
            self._shutdown()
            raise
        backoff = 2
        while not self.stopping:
            code = self._run_once(dest)
            if self.stopping or self.max_seconds and (time.monotonic() - self.started) >= self.max_seconds:
                break
            log("RTMPS HEALTH", value="down")
            log("ENCODER HEALTH", value="restarting", code=code)
            time.sleep(backoff)
            backoff = min(backoff + 2, 15)
            self.connected = False
        if self.program is not None:
            self.program.close()
        self._shutdown()
        log("STATION STOP")
        return 0

    def _shutdown(self):
        if self.session is not None:
            self.session.finish()
            self.session = None
        if self.capture is not None:
            self.capture.stop()
            self.capture = None


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(Station().run())
