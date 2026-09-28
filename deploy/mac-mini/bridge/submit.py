#!/usr/bin/env python3
"""Submit one media item to multiple Postiz integrations without duplicate retries.

POSTIZ_API_URL must be the self-hosted backend URL, e.g. http://127.0.0.1:4007/api
on the Mac mini, or https://postiz.example.org/api for small remote requests.
POSTIZ_API_KEY is the API key created in Postiz. Neither is saved in the state DB.
"""

import hashlib
import http.client
import json
import mimetypes
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def load_job(path):
    job = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(job, dict):
        raise ValueError("Job must be a JSON object")
    for key in ("id", "media_path", "caption", "integrations"):
        if key not in job:
            raise ValueError(f"Missing {key}")
    if not isinstance(job["id"], str) or not job["id"].strip():
        raise ValueError("id must be a nonempty string")
    if not isinstance(job["caption"], str):
        raise ValueError("caption must be a string")
    if not isinstance(job["integrations"], list) or not job["integrations"]:
        raise ValueError("integrations must be a nonempty list")
    ids = []
    for integration in job["integrations"]:
        if not isinstance(integration, dict) or not isinstance(integration.get("id"), str):
            raise ValueError("Each integration needs an id")
        if not isinstance(integration.get("settings", {}), dict):
            raise ValueError("Integration settings must be an object")
        ids.append(integration["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate integration IDs")
    mode = job.get("mode", "draft")
    if mode not in ("draft", "now", "schedule"):
        raise ValueError("mode must be draft, now or schedule")
    if mode == "schedule":
        date = job.get("date")
        if not isinstance(date, str):
            raise ValueError("Scheduled jobs need an ISO date")
        datetime.fromisoformat(date.replace("Z", "+00:00"))
    media = Path(job["media_path"]).expanduser().resolve()
    if not media.is_file():
        raise ValueError(f"Media file not found: {media}")
    return job, media


def digest_job(job, media):
    digest = hashlib.sha256(json.dumps(job, sort_keys=True).encode("utf-8"))
    with media.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def connection():
    url = urlsplit(os.environ.get("POSTIZ_API_URL", ""))
    local = url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost", "::1")
    if not (url.scheme == "https" or local) or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("POSTIZ_API_URL must use HTTPS or loopback HTTP and end in /api")
    if url.path.rstrip("/") != "/api":
        raise ValueError("POSTIZ_API_URL must end in /api")
    key = os.environ.get("POSTIZ_API_KEY")
    if not key:
        raise ValueError("POSTIZ_API_KEY is required")
    client = http.client.HTTPConnection if local else http.client.HTTPSConnection
    return client(url.hostname, url.port or (80 if local else 443), timeout=120), key


def decode_response(response):
    body = response.read(1024 * 1024 + 1)
    if len(body) > 1024 * 1024:
        raise RuntimeError("Postiz response exceeded 1 MB")
    if response.status < 200 or response.status >= 300:
        raise RuntimeError(f"Postiz returned HTTP {response.status}: {body[:500].decode('utf-8', 'replace')}")
    return json.loads(body)


def upload(media):
    conn, key = connection()
    boundary = uuid.uuid4().hex
    filename = media.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")
    suffix = f"\r\n--{boundary}--\r\n".encode("ascii")
    try:
        conn.putrequest("POST", "/api/public/v1/upload")
        conn.putheader("Authorization", key)
        conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
        conn.putheader("Content-Length", str(len(prefix) + media.stat().st_size + len(suffix)))
        conn.endheaders()
        conn.send(prefix)
        with media.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                conn.send(chunk)
        conn.send(suffix)
        result = decode_response(conn.getresponse())
    finally:
        conn.close()
    if not isinstance(result, dict) or not result.get("id") or not result.get("path"):
        raise RuntimeError("Postiz upload returned no media id/path")
    return {"id": result["id"], "path": result["path"]}


def submit(job, media_record):
    conn, key = connection()
    date = job.get("date") or datetime.now(timezone.utc).isoformat()
    body = {
        "type": job.get("mode", "draft"),
        "date": date,
        "shortLink": False,
        "tags": [],
        "creationMethod": "API",
        "posts": [
            {
                "integration": {"id": item["id"]},
                "value": [{"content": job["caption"], "image": [media_record]}],
                "settings": item.get("settings", {}),
            }
            for item in job["integrations"]
        ],
    }
    data = json.dumps(body).encode("utf-8")
    try:
        conn.request(
            "POST", "/api/public/v1/posts", data,
            {"Authorization": key, "Content-Type": "application/json"},
        )
        result = decode_response(conn.getresponse())
    finally:
        conn.close()
    if not isinstance(result, list) or len(result) != len(job["integrations"]):
        raise RuntimeError("Postiz did not confirm every destination; reconcile manually")
    return result


def main():
    if len(sys.argv) != 3:
        raise ValueError("Usage: submit.py job.json state.sqlite")
    job, media = load_job(sys.argv[1])
    fingerprint = digest_job(job, media)
    state = Path(sys.argv[2]).expanduser().resolve()
    state.parent.mkdir(parents=True, exist_ok=True)
    os.umask(0o077)
    with sqlite3.connect(state) as db:
        db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, status TEXT NOT NULL, result TEXT)")
        # Serialize submitters through the upload phase. A second process must
        # not see the same job as available while this one is preparing it.
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR IGNORE INTO jobs VALUES (?, ?, 'preparing', NULL)", (job["id"], fingerprint))
        saved = db.execute("SELECT fingerprint, status, result FROM jobs WHERE id=?", (job["id"],)).fetchone()
        if saved[0] != fingerprint:
            raise ValueError("Job id was previously used with different content or media")
        if saved[1] == "accepted":
            print(saved[2])
            return
        if saved[1] != "preparing":
            raise RuntimeError("Submission outcome is uncertain. Check Postiz before any retry; use a new job id only after reconciliation.")
        media_record = upload(media)
        # This state is committed before sending: a timeout or partial response
        # must never trigger an automatic second publication.
        db.execute("UPDATE jobs SET status='uncertain' WHERE id=?", (job["id"],))
        db.commit()
        result = submit(job, media_record)
        output = json.dumps(result)
        db.execute("UPDATE jobs SET status='accepted', result=? WHERE id=?", (output, job["id"]))
        db.commit()
        print(output)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
