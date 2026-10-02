"""Capture the public live desk.

The picture is the page. The sound is the radio MP3 itself, not the browser's
audio device, so a pause inside Chromium does not cut the broadcast.
"""

import os
import shutil
import subprocess
import time

RADIO = "https://api.rootrecord.cloud/radio/live.mp3"


class PageCapture:
    def __init__(self, url, display=":99", size="1280x720"):
        self.url = url
        self.display = display
        self.size = size
        self.sink = "rr-broadcast"
        self.procs = []

    def available(self):
        needed = ["Xvfb", self._browser()]
        return [name for name in needed if name and shutil.which(name) is None]

    def _browser(self):
        for name in ("chromium", "chromium-browser", "google-chrome"):
            if shutil.which(name):
                return name
        return "chromium"

    def start(self):
        missing = self.available()
        if missing:
            raise RuntimeError("Page capture needs: " + ", ".join(missing))
        width, height = self.size.split("x", 1)
        self.procs.append(subprocess.Popen(
            ["Xvfb", self.display, "-screen", "0", f"{width}x{height}x24"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ))
        time.sleep(0.4)
        env = os.environ.copy()
        env["DISPLAY"] = self.display
        profile = "/tmp/rr-chromium-profile"
        os.makedirs(profile, exist_ok=True)
        log = open("/tmp/rr-chromium.log", "ab")
        self.procs.append(subprocess.Popen(
            [
                self._browser(),
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--disable-fre",
                "--ozone-platform=x11",
                "--in-process-gpu",
                "--disable-gpu-sandbox",
                "--ignore-gpu-blocklist",
                "--enable-webgl",
                "--enable-unsafe-swiftshader",
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--mute-audio",
                "--autoplay-policy=no-user-gesture-required",
                "--user-data-dir=" + profile,
                f"--window-size={width},{height}",
                "--window-position=0,0",
                "--kiosk",
                self.url,
            ],
            env=env,
            stdout=log,
            stderr=log,
        ))
        time.sleep(20)
        if self.procs[-1].poll() is not None:
            raise RuntimeError("capture browser exited before the page painted")

    def ffmpeg_inputs(self):
        return [
            "-f", "x11grab", "-draw_mouse", "0",
            "-video_size", self.size, "-framerate", "15",
            "-i", self.display,
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "2",
            "-i", RADIO,
        ]

    def stop(self):
        for proc in reversed(self.procs):
            if proc.poll() is None:
                proc.terminate()
        for proc in self.procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.procs = []
