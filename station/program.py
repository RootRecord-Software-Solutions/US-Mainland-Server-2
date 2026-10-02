"""Local station program. Music under the voice, chimes hold a report."""

import array
import random
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HAWAII = ZoneInfo("Pacific/Honolulu")
RATE = 48000
CHANNELS = 2
FRAME = RATE * CHANNELS * 2 // 10
AUDIO_EXT = {".wav", ".ogg", ".mp3", ".flac", ".m4a"}
DUCK = 0.25


def mix_pcm(parts):
    """Add s16le chunks. Each part is (bytes, gain)."""
    acc = None
    for raw, gain in parts:
        if not raw or gain == 0:
            continue
        samples = array.array("h")
        samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
        if acc is None:
            acc = array.array("h", (0,)) * len(samples)
        limit = min(len(acc), len(samples))
        for i in range(limit):
            acc[i] = max(-32768, min(32767, acc[i] + int(samples[i] * gain)))
    if acc is None:
        return bytes(FRAME)
    return acc.tobytes()


def chime_slot(when):
    """Return hour-HH-MM when Hawaii is at :00 or :30, else ''."""
    local = when.astimezone(HAWAII)
    if local.minute not in (0, 30):
        return ""
    return local.strftime("hour-%H-%M")


def slot_key(when):
    local = when.astimezone(HAWAII)
    name = chime_slot(when)
    if not name:
        return ""
    return local.strftime("%Y-%m-%d-") + name


class Library:
    def __init__(self, root):
        self.root = Path(root)

    def files(self, kind):
        folder = self.root / kind
        if not folder.is_dir():
            return []
        found = []
        for path in folder.iterdir():
            if path.is_file() and path.suffix.lower() in AUDIO_EXT:
                found.append(path)
        return sorted(found)

    def chime(self, name):
        folder = self.root / "chimes"
        if not name or not folder.is_dir():
            return None
        for ext in (".wav", ".ogg", ".mp3", ".flac"):
            path = folder / (name + ext)
            if path.is_file():
                return path
        return None


class Decoder:
    def __init__(self, path):
        self.path = path
        self.buf = b""
        self.done = False
        self.proc = subprocess.Popen(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", str(path),
                "-f", "s16le", "-ar", str(RATE), "-ac", str(CHANNELS),
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def take(self):
        while len(self.buf) < FRAME and not self.done:
            chunk = self.proc.stdout.read(FRAME)
            if not chunk:
                self.done = True
                break
            self.buf += chunk
        if len(self.buf) < FRAME:
            if not self.buf:
                return b"", True
            padded = self.buf + bytes(FRAME - len(self.buf))
            self.buf = b""
            return padded, True
        frame, self.buf = self.buf[:FRAME], self.buf[FRAME:]
        return frame, False

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()
        try:
            self.proc.stdout.close()
        except Exception:
            pass
        self.proc.wait(timeout=2)


class Program:
    """Pick local files and mix one PCM frame at a time."""

    def __init__(self, root, now=None, shuffle=None):
        self.lib = Library(root)
        self.now = now or datetime.now
        self.shuffle = shuffle or random.shuffle
        self.music_order = []
        self.music = None
        self.report = None
        self.report_id = None
        self.finished_report = None
        self.chime = None
        self.played_chime = ""
        self.ident = None
        self.id_index = 0
        self.title = "Standing by"
        self._scan_in = 0

    def close(self):
        for dec in (self.music, self.report, self.chime, self.ident):
            if dec is not None:
                dec.close()
        self.music = self.report = self.chime = self.ident = None

    def _open_music(self):
        if self.music is not None:
            self.music.close()
            self.music = None
        if not self.music_order:
            self.music_order = self.lib.files("music")
            self.shuffle(self.music_order)
        if not self.music_order:
            self.title = "Standing by"
            return
        path = self.music_order.pop(0)
        self.music = Decoder(path)
        if self.report is None:
            self.title = path.stem.replace("_", " ")

    def _scan(self):
        self._scan_in -= 1
        if self._scan_in > 0:
            return
        self._scan_in = 20
        reports = [p for p in self.lib.files("reports") if "_current" in p.stem]
        if not reports:
            reports = self.lib.files("reports")
        if not reports:
            return
        newest = max(reports, key=lambda p: p.stat().st_mtime_ns)
        ident = (str(newest), newest.stat().st_mtime_ns)
        if ident == self.finished_report or ident == self.report_id:
            return
        if self.report is not None:
            return
        self.report = Decoder(newest)
        self.report_id = ident
        self.title = newest.stem.replace("_current", "").replace("_", " ").strip() or "Report"

    def read_frame(self):
        self._scan()
        when = self.now(HAWAII)
        key = slot_key(when)
        if key and key != self.played_chime and self.chime is None:
            path = self.lib.chime(chime_slot(when))
            if path is not None:
                self.chime = Decoder(path)
                self.played_chime = key
                self.title = "Time"

        parts = []
        if self.chime is not None:
            frame, ended = self.chime.take()
            if frame:
                parts.append((frame, 1.0))
            if self.music is not None:
                bed, bed_ended = self.music.take()
                if bed:
                    parts.append((bed, DUCK))
                if bed_ended:
                    self.music.close()
                    self.music = None
            if ended:
                self.chime.close()
                self.chime = None
            return mix_pcm(parts), self.title

        if self.ident is not None:
            frame, ended = self.ident.take()
            if frame:
                parts.append((frame, 1.0))
            if ended:
                self.ident.close()
                self.ident = None
                self._open_music()
            return mix_pcm(parts), self.title

        if self.music is None and self.report is None:
            ids = self.lib.files("ids")
            if ids:
                self.ident = Decoder(ids[self.id_index % len(ids)])
                self.id_index += 1
                self.title = "Station"
                frame, _ended = self.ident.take()
                if frame:
                    parts.append((frame, 1.0))
                return mix_pcm(parts), self.title
            self._open_music()
        elif self.music is None:
            self._open_music()

        music_gain = DUCK if self.report is not None else 1.0
        if self.music is not None:
            frame, ended = self.music.take()
            if frame:
                parts.append((frame, music_gain))
            if ended:
                self.music.close()
                self.music = None
        if self.report is not None:
            frame, ended = self.report.take()
            if frame:
                parts.append((frame, 1.0))
            if ended:
                self.finished_report = self.report_id
                self.report.close()
                self.report = None
                if self.music is not None:
                    self.title = self.music.path.stem.replace("_", " ")
                else:
                    self.title = "Standing by"
        return mix_pcm(parts), self.title
