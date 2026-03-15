"""
YouTube upload module — OAuth2 authentication and video upload.

Requires client_secret.json from Google Cloud Console at:
    ~/.config/manimator/client_secret.json

Token stored at:
    ~/.config/manimator/youtube_token.json

Google SDK imports are lazy (same pattern as llm.py) to avoid requiring
google-api-python-client for users who don't need upload functionality.
"""

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "manimator"
CLIENT_SECRET_PATH = CONFIG_DIR / "client_secret.json"
TOKEN_PATH = CONFIG_DIR / "youtube_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _get_credentials():
    """Load existing token or run OAuth2 InstalledAppFlow browser consent.

    Returns:
        google.oauth2.credentials.Credentials

    Raises:
        FileNotFoundError: If client_secret.json is missing.
    """
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRET_PATH.exists():
        raise FileNotFoundError(
            f"YouTube client secret not found at {CLIENT_SECRET_PATH}. "
            "Download it from Google Cloud Console → APIs & Services → Credentials."
        )

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
        os.chmod(TOKEN_PATH, 0o600)
        log.info("YouTube credentials saved to %s", TOKEN_PATH)

    return creds


def _build_youtube_service():
    """Build an authenticated YouTube Data API v3 service object."""
    from googleapiclient.discovery import build

    creds = _get_credentials()
    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    category_id: str = "28",
    privacy: str = "private",
    thumbnail_path: str | None = None,
) -> dict:
    """Upload a video to YouTube.

    Args:
        video_path: Path to video file.
        title: Video title (truncated to 100 chars).
        description: Video description.
        tags: List of tag strings.
        category_id: YouTube category (28 = Science & Technology).
        privacy: One of "private", "unlisted", "public".
        thumbnail_path: Optional path to custom thumbnail image.

    Returns:
        dict with keys: video_id, url, status.

    Raises:
        FileNotFoundError: If video file doesn't exist.
        ValueError: If privacy is not valid.
    """
    from googleapiclient.http import MediaFileUpload

    video = Path(video_path)
    if not video.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if privacy not in ("private", "unlisted", "public"):
        raise ValueError(f"Invalid privacy setting: {privacy}. Must be private, unlisted, or public.")

    title = title[:100]

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video), resumable=True, chunksize=10 * 1024 * 1024  # 10 MB chunks
    )

    youtube = _build_youtube_service()
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            log.info("Upload progress: %.1f%%", status.progress() * 100)

    video_id = response["id"]
    log.info("Upload complete: video_id=%s", video_id)

    # Set custom thumbnail if provided
    if thumbnail_path and Path(thumbnail_path).exists():
        thumb_media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
        youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
        log.info("Thumbnail set for video %s", video_id)

    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "status": response.get("status", {}).get("uploadStatus", "uploaded"),
    }


def upload_short(
    video_path: str,
    storyboard_data: dict,
    privacy: str = "private",
    platform: str = "youtube_short",
) -> dict:
    """Upload a short-form video with auto-generated metadata.

    Uses social.generate_post_copy() for title/description/tags and
    renderer.generate_thumbnail() for the thumbnail.

    Args:
        video_path: Path to rendered video.
        storyboard_data: Storyboard dict with 'meta' and 'scenes'.
        privacy: Upload privacy setting.
        platform: Social platform for copy generation.

    Returns:
        dict with keys: video_id, url, status.
    """
    from manimator.social import generate_post_copy
    from manimator.renderer import generate_thumbnail

    copy = generate_post_copy(storyboard_data, platform)

    title = copy.get("hook_text", storyboard_data.get("meta", {}).get("title", ""))[:100]
    hashtags = copy.get("hashtags", [])
    caption = copy.get("caption", "")

    # Prepend #Shorts to description for YouTube Shorts discovery
    description = "#Shorts\n\n" + caption

    tags = [h.lstrip("#") for h in hashtags]

    # Generate thumbnail
    thumb_path = Path(video_path).with_suffix(".jpg")
    try:
        generate_thumbnail(Path(video_path), thumb_path)
        thumbnail = str(thumb_path)
    except Exception as e:
        log.warning("Thumbnail generation failed: %s", e)
        thumbnail = None

    return upload_video(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        privacy=privacy,
        thumbnail_path=thumbnail,
    )
