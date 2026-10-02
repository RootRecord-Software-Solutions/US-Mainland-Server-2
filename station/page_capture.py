"""Capture the public live desk. Chromium is off unless STATION_VISUAL=page.

Xvfb plus a Pulse null sink is the light capture that can hand the page's
picture and the radio autoplay to one FFmpeg process. Headless Chrome does
not expose that audio reliably. This box is a t3.micro, so the path stays
opt-in and the default encoder remains the generated slate.
"""

import os
import shutil
import subprocess
import time


class PageCapture:
    def __init__(self, url, display=":99", size="1280x720"):
        self.url = url
        self.display = display
        self.size = size
        self.sink = "rr-broadcast"
        self.procs = []

    def available(self):
        needed = ["Xvfb", "pactl", self._browser()]
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
        subprocess.run(
            ["pactl", "load-module", "module-null-sink", f"sink_name={self.sink}"],
            check=False,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        env["PULSE_SINK"] = self.sink
        self.procs.append(subprocess.Popen(
            [
                self._browser(),
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-gpu",
                "--use-gl=swiftshader",
                f"--window-size={width},{height}",
                "--window-position=0,0",
                "--kiosk",
                self.url,
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ))
        time.sleep(2)

    def ffmpeg_inputs(self):
        return [
            "-f", "x11grab", "-video_size", self.size, "-framerate", "15",
            "-i", self.display,
            "-f", "pulse", "-i", f"{self.sink}.monitor",
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
        subprocess.run(
            ["pactl", "unload-module", "module-null-sink"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
