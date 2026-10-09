import html
import json
import logging
import os
import re
import sys
import time

import feedparser
import requests
from requests_oauthlib import OAuth1

FEED_URL = os.environ["FEED_URL"]
API_KEY = os.environ["X_API_KEY"]
API_SECRET = os.environ["X_API_SECRET"]
ACCESS_TOKEN = os.environ["X_ACCESS_TOKEN"]
ACCESS_TOKEN_SECRET = os.environ["X_ACCESS_TOKEN_SECRET"]

SEEN_FILE = os.getenv("SEEN_FILE", "seen_x.json")
RUN_MODE = os.getenv("RUN_MODE", "normal")  # normal | upload_test
MAX_POSTS_PER_RUN = int(os.getenv("MAX_POSTS_PER_RUN", "5"))
ENGLISH_ONLY = os.getenv("ENGLISH_ONLY", "1") == "1"
ALLOW_TEXT_ONLY = os.getenv("ALLOW_TEXT_ONLY", "0") == "1"
MAX_TEXT = 270  # X's limit is 280; keep a safety margin

UPLOAD_URL = "https://api.x.com/2/media/upload"
POST_URL = "https://api.x.com/2/tweets"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
AUTH = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
DUB_RE = re.compile(r"\(([^()]*?)\s+Dub\)", re.I)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


# ---------- helpers ----------

def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f)


def entry_id(entry):
    return entry.get("id") or entry.get("link") or entry.get("title")


def clean_text(raw):
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def truncate(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:!?-") + "…"


def is_english(entry):
    """Skip items tagged as a non-English dub, e.g. '(Telugu Dub)'."""
    match = DUB_RE.search(entry.get("title", ""))
    return match is None or match.group(1).strip().lower() in ("english", "en")


def get_image_url(entry):
    thumbs = entry.get("media_thumbnail", [])

    def width(t):
        try:
            return int(t.get("width", 0))
        except (TypeError, ValueError):
            return 0

    if thumbs:
        best = max(thumbs, key=width)
        if best.get("url"):
            return best["url"]
    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and link.get("type", "").startswith("image"):
            return link.get("href")
    match = re.search(r'<img[^>]+src=["\']([^"\']+)', entry.get("summary", ""), re.I)
    return match.group(1) if match else None


def compose_text(entry):
    title = truncate(clean_text(entry.get("title", "")), 140)
    summary = clean_text(entry.get("summary", ""))
    text = title
    room = MAX_TEXT - len(title) - 2
    if summary and room >= 40:
        text += "\n\n" + truncate(summary, room)
    return text


# ---------- X API ----------

def download_image(url):
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    if len(r.content) > 5_000_000:
        raise ValueError("image larger than 5 MB")
    ctype = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
    return r.content, ctype


def upload_media(content, ctype):
    ext = "png" if ctype == "image/png" else "jpg"
    r = requests.post(
        UPLOAD_URL,
        auth=AUTH,
        files={"media": (f"image.{ext}", content, ctype)},
        data={"media_category": "tweet_image"},
        timeout=60,
    )
    if not r.ok:
        logging.error("Media upload failed: HTTP %s %s", r.status_code, r.text[:300])
        return None
    body = r.json()
    media_id = (body.get("data") or {}).get("id") or body.get("media_id_string")
    if not media_id:
        logging.error("Media upload gave no id: %s", r.text[:300])
        return None
    return str(media_id)


def create_post(text, media_id=None):
    payload = {"text": text}
    if media_id:
        payload["media"] = {"media_ids": [media_id]}
    r = requests.post(POST_URL, auth=AUTH, json=payload, timeout=30)
    if r.status_code in (200, 201):
        return (r.json().get("data") or {}).get("id")
    logging.error("Post failed: HTTP %s %s", r.status_code, r.text[:300])
    return None


def publish(entry):
    text = compose_text(entry)
    media_id = None
    image_url = get_image_url(entry)
    if image_url:
        try:
            content, ctype = download_image(image_url)
            media_id = upload_media(content, ctype)
        except (requests.RequestException, ValueError) as exc:
            logging.error("Image problem: %s", exc)
    if not media_id and not ALLOW_TEXT_ONLY:
        logging.error("No image attached, so not posting (set ALLOW_TEXT_ONLY=1 to allow)")
        return False
    post_id = create_post(text, media_id)
    if post_id:
        logging.info("Posted %s: %s", post_id, entry.get("title"))
        return True
    return False


# ---------- main flow ----------

def fetch_entries():
    r = requests.get(FEED_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    return [e for e in feed.entries if entry_id(e)]


def upload_test(entries):
    entry = next((e for e in entries if is_english(e)), entries[0])
    url = get_image_url(entry)
    logging.info("Test image: %s", url)
    content, ctype = download_image(url)
    media_id = upload_media(content, ctype)
    if media_id:
        logging.info("Upload test OK, media id %s", media_id)
    else:
        logging.error("Upload test FAILED (see error above)")
        sys.exit(1)


def run():
    entries = fetch_entries()
    logging.info("Feed returned %d entries", len(entries))
    if not entries:
        return

    if RUN_MODE == "upload_test":
        upload_test(entries)
        return

    seen = load_seen()
    if not seen:  # first run: remember what's there, post nothing
        save_seen({entry_id(e) for e in entries})
        logging.info("First run: marked %d existing items as seen", len(entries))
        return

    new = [e for e in entries if entry_id(e) not in seen]
    todo = []
    for e in new:
        if ENGLISH_ONLY and not is_english(e):
            seen.add(entry_id(e))  # skipped on purpose
        else:
            todo.append(e)
    todo.sort(key=lambda e: e.get("published_parsed") or (0,) * 9)  # oldest first
    logging.info("%d new items to post (%d skipped)", len(todo), len(new) - len(todo))

    posted = 0
    for e in todo:
        if posted >= MAX_POSTS_PER_RUN:
            logging.info("Cap reached, %d items wait for the next run", len(todo) - posted)
            break
        if not publish(e):
            break  # stop at the first failure so we don't waste credits
        seen.add(entry_id(e))
        save_seen(seen)
        posted += 1
        time.sleep(3)
    save_seen(seen)


if __name__ == "__main__":
    run()
