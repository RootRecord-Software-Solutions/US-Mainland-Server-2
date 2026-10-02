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

`station/youtube_station.py` decides what is on. FFmpeg draws the slate, encodes H.264/AAC, and sends RTMPS. The unit is installed stopped:

```bash
sudo systemctl start rr-youtube-station
sudo systemctl stop rr-youtube-station
```

The ingest URL and stream key belong in `/etc/rootrecord/youtube.env` on the machine. That file is not in this repository. Without `YOUTUBE_KEY`, the process exits and does not restart.

`STATION_MODE=slate` sends a generated picture and tone. `STATION_MODE=program` mixes local files under `/var/lib/rootrecord/station/{music,chimes,reports,ids}`. Music stays under a report. A Hawaii :00 or :30 chime holds the report. Video is capped at 1000k, audio at 128k.
