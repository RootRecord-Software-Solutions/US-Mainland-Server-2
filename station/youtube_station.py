#!/usr/bin/env python3
"""Start and watch one FFmpeg process for the YouTube station.

Python chooses the program. FFmpeg sends the picture, the sound, and RTMPS.
The stream key is read from the environment, never from this repository.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from program import Program

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
VIDEO_BITRATE = "800k"
VIDEO_MAXRATE = "1000k"
AUDIO_BITRATE = "128k"


def log(event, **fields):
    extra = " ".join(f"{key}={value}" for key, value in fields.items())
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
        self.max_seconds = env_int("STATION_MAX_SECONDS")
        self.state = self.root / "state"
        self.slate = self.state / "slate.txt"
        self.progress = self.state / "ffmpeg-progress.txt"
        self.proc = None
        self.program = None
        self.started = time.monotonic()
        self.connected = False

    def stop(self, *_args):
        self.stopping = True
        self._end_ffmpeg()

    def _destination(self):
        if self.sink == "file":
            return str(self.state / "preview.mkv")
        if not self.key:
            log("STATION STOP", reason="missing_youtube_key")
            raise SystemExit(2)
        return f"{self.url}/{self.key}"

    def _write_slate(self, title):
        self.state.mkdir(parents=True, exist_ok=True)
        text = title.replace("\n", " ").strip() or "Standing by"
        self.slate.write_text(text + "\n", encoding="utf-8")

    def _filters(self):
        clock = "drawtext=fontfile=%s:text='%%{localtime\\:%%H\\:%%M} HST':fontsize=28:fontcolor=white:x=(w-text_w)/2:y=h/2+56" % FONT
        title = "drawtext=fontfile=%s:textfile=%s:reload=1:fontsize=36:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" % (FONT, self.slate)
        name = "drawtext=fontfile=%s:text='ROOTRECORD':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=h/2-78" % FONT
        site = "drawtext=fontfile=%s:text='rootrecord.cloud':fontsize=24:fontcolor=white:x=(w-text_w)/2:y=h-72" % FONT
        return ",".join([name, title, clock, site])

    def _command(self, dest):
        video = [
            "-f", "lavfi", "-i", "color=c=0x0e1a14:s=1280x720:r=15",
        ]
        if self.mode == "program":
            audio = ["-f", "s16le", "-ar", "48000", "-ac", "2", "-i", "pipe:0"]
        else:
            audio = ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning",
            *video, *audio,
            "-vf", self._filters(),
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
            "-b:v", VIDEO_BITRATE, "-maxrate", VIDEO_MAXRATE, "-bufsize", "1600k",
            "-pix_fmt", "yuv420p", "-g", "30",
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
        log("FFMPEG START", mode=self.mode, sink=self.sink, video=VIDEO_MAXRATE, audio=AUDIO_BITRATE)
        stdin = subprocess.PIPE if self.mode == "program" else subprocess.DEVNULL
        self.proc = subprocess.Popen(cmd, stdin=stdin, stderr=subprocess.PIPE)
        self.born = time.monotonic()
        self.connected = False
        next_log = time.monotonic() + 5
        try:
            while not self.stopping:
                if self.max_seconds and (time.monotonic() - self.started) >= self.max_seconds:
                    self.stopping = True
                    break
                if self.proc.poll() is not None:
                    break
                if self.mode == "program":
                    frame, title = self.program.read_frame()
                    if title:
                        self._write_slate(title)
                    try:
                        self.proc.stdin.write(frame)
                    except BrokenPipeError:
                        break
                if time.monotonic() >= next_log:
                    self._watch_progress()
                    if self.mode == "program":
                        log("PROGRAM", value=self.program.title)
                    next_log = time.monotonic() + 5
                if self.mode != "program":
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
        return self.proc.returncode

    def run(self):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        self.state.mkdir(parents=True, exist_ok=True)
        if self.mode == "program":
            self.program = Program(self.root)
        log("STATION START", mode=self.mode, sink=self.sink)
        try:
            dest = self._destination()
        except SystemExit:
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
        log("STATION STOP")
        return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(Station().run())
