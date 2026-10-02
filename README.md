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
