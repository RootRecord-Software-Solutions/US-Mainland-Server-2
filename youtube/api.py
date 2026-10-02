"""Authenticated YouTube Data API v3 calls. No station scheduling here."""

from youtube.errors import AuthRequired, BroadcastError


def client(credentials):
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def _call(fn):
    from googleapiclient.errors import HttpError
    try:
        return fn()
    except HttpError as exc:
        status = getattr(exc.resp, "status", "")
        reason = ""
        try:
            body = json_reason(exc)
            reason = body
        except Exception:
            reason = "request failed"
        if status in (401, 403) and "insufficientPermissions" in reason:
            raise AuthRequired("insufficientPermissions") from None
        if status in (401, 403):
            raise AuthRequired(f"YouTube refused the request ({status}).") from None
        raise BroadcastError(f"YouTube API error ({status}).") from None


def json_reason(exc):
    import json
    raw = exc.content.decode("utf-8", errors="replace") if exc.content else ""
    data = json.loads(raw) if raw else {}
    errors = ((data.get("error") or {}).get("errors") or [])
    if errors:
        return errors[0].get("reason") or ""
    return ""


def get_channel(youtube):
    return _call(lambda: youtube.channels().list(part="id,snippet", mine=True).execute())


def list_streams(youtube):
    return _call(lambda: youtube.liveStreams().list(
        part="id,snippet,cdn,status", mine=True, maxResults=50
    ).execute())


def create_stream(youtube, title, resolution, frame_rate):
    body = {
        "snippet": {"title": title},
        "cdn": {
            "ingestionType": "rtmp",
            "resolution": resolution,
            "frameRate": frame_rate,
        },
    }
    return _call(lambda: youtube.liveStreams().insert(part="id,snippet,cdn,status", body=body).execute())


def get_stream(youtube, stream_id):
    return _call(lambda: youtube.liveStreams().list(
        part="id,snippet,cdn,status", id=stream_id
    ).execute())


def create_broadcast(youtube, body):
    return _call(lambda: youtube.liveBroadcasts().insert(
        part="id,snippet,status,contentDetails", body=body
    ).execute())


def bind_broadcast(youtube, broadcast_id, stream_id):
    return _call(lambda: youtube.liveBroadcasts().bind(
        id=broadcast_id, streamId=stream_id, part="id,contentDetails,status"
    ).execute())


def transition_broadcast(youtube, broadcast_id, status):
    return _call(lambda: youtube.liveBroadcasts().transition(
        broadcastStatus=status, id=broadcast_id, part="id,status"
    ).execute())


def get_broadcast(youtube, broadcast_id):
    return _call(lambda: youtube.liveBroadcasts().list(
        part="id,snippet,status,contentDetails", id=broadcast_id
    ).execute())


def delete_broadcast(youtube, broadcast_id):
    return _call(lambda: youtube.liveBroadcasts().delete(id=broadcast_id).execute())


def stream_is_active(stream):
    return ((stream.get("status") or {}).get("streamStatus") == "active")
