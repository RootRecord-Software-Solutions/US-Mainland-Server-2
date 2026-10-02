# US Mainland Server 2

YouTube station checkout for `rr-streaming`. This repository holds station code and configuration. Generated WAV, OGG, and MP3 stay on the machine and are not committed.

`scripts/aws-git-pull.sh` does three things:

1. Enter `/home/ubuntu/US-Mainland-Server-2`
2. Refuse to pull when tracked files have local modifications
3. `git pull --ff-only`

Untracked files do not block the pull. The script does not restart services, handle audio, or read credentials.

The timer runs one minute after boot and one minute after each run (`OnBootSec=1min`, `OnUnitActiveSec=1min`, `AccuracySec=10s`, `Persistent=true`).

On the station, after the first clone:

```bash
sudo cp systemd/aws-git-pull.service systemd/aws-git-pull.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aws-git-pull.timer
```

The desk pushes. The station only pulls over HTTPS.

This station does not pull files from the other mainland server. Generated WAV, OGG, and MP3 stay in `/var/lib/rootrecord/station/` and are not committed.

## YouTube

`station/youtube_station.py` decides what is on. FFmpeg encodes H.264/AAC and sends RTMPS. The picture is a generated slate unless `STATION_VISUAL=page`, which captures `https://www.rootrecord.cloud/live?broadcast=1`. That page is the existing live desk. The `broadcast=1` query is what starts the radio autoplay. The public `/live` page does not.

Page capture uses Xvfb, a Pulse null sink, and Chromium, because that is the light path that lets FFmpeg hear the page. It stays off until those programs are installed and `STATION_VISUAL=page` is set. This machine is a `t3.micro`, so that path is not the default.

The unit is installed stopped:

```bash
sudo systemctl start rr-youtube-station
sudo systemctl stop rr-youtube-station
```

Secrets stay in `/etc/rootrecord/youtube/` (`client_secret.json`, `token.json`). They are not in this repository. Placeholders are in `config/youtube.env.example`.

```bash
python3 -m youtube.auth
python3 -m youtube.status
```

The API finds one reusable stream, opens one broadcast, and binds them. FFmpeg restarts reuse that broadcast. A missing token stops the station instead of retrying.

`STATION_MODE=slate` sends a generated picture and tone. `STATION_MODE=program` mixes local files under `/var/lib/rootrecord/station/{music,chimes,reports,ids}`. Video is capped at 1000k, audio at 128k.
