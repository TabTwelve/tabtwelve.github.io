#!/usr/bin/env python3
"""Fetch the channel's public videos from YouTube's RSS feed into data/videos.json.

No API key needed. The feed lists the 15 most recent public uploads. If the
fetch fails for any reason the existing data/videos.json is left untouched, so
a YouTube hiccup never blanks the site.

When run inside GitHub Actions it writes `changed=true|false` to $GITHUB_OUTPUT
so the workflow can skip a redeploy when nothing is new.
"""
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "site.config.json").read_text(encoding="utf-8"))
DATA = ROOT / "data" / "videos.json"

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
UA = "Mozilla/5.0 (compatible; tabtwelve-site-builder/1.0; +https://tabtwelve.com)"


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def resolve_channel_id() -> str:
    """Use the configured channel id, or look it up from the handle page."""
    cid = (CONFIG.get("youtube", {}).get("channel_id") or "").strip()
    if re.fullmatch(r"UC[\w-]{22}", cid):
        return cid
    handle = CONFIG["youtube"]["handle"].lstrip("@")
    html = http_get(f"https://www.youtube.com/@{handle}").decode("utf-8", "replace")
    m = re.search(r'"channelId":"(UC[\w-]{22})"', html) or re.search(r"/channel/(UC[\w-]{22})", html)
    if not m:
        raise RuntimeError("Could not find the channel id on the handle page")
    return m.group(1)


def parse_feed(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    videos = []
    for entry in root.findall("atom:entry", NS):
        vid = entry.findtext("yt:videoId", default="", namespaces=NS).strip()
        if not vid:
            continue
        group = entry.find("media:group", NS)
        desc = ""
        thumb = ""
        if group is not None:
            desc = (group.findtext("media:description", default="", namespaces=NS) or "").strip()
            t = group.find("media:thumbnail", NS)
            if t is not None:
                thumb = t.get("url", "")
        # View counts and "updated" stamps are left out on purpose: they change
        # constantly and would make every hourly run look like new content.
        videos.append(
            {
                "id": vid,
                "title": (entry.findtext("atom:title", default="", namespaces=NS) or "").strip(),
                "published": (entry.findtext("atom:published", default="", namespaces=NS) or "").strip(),
                "description": desc,
                "thumbnail": thumb or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            }
        )
    videos.sort(key=lambda v: v["published"], reverse=True)
    return videos


def write_output(changed: bool) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"changed={'true' if changed else 'false'}\n")


def main() -> int:
    DATA.parent.mkdir(parents=True, exist_ok=True)
    old_text = DATA.read_text(encoding="utf-8") if DATA.exists() else None
    try:
        cid = resolve_channel_id()
        feed = http_get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
        videos = parse_feed(feed)
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: could not fetch the YouTube feed ({exc}). Keeping the existing video list.", file=sys.stderr)
        if old_text is None:
            DATA.write_text("[]\n", encoding="utf-8")
        write_output(False)
        return 0

    new_text = json.dumps(videos, indent=2, ensure_ascii=False) + "\n"
    changed = new_text != old_text
    if changed:
        DATA.write_text(new_text, encoding="utf-8")
    print(f"Fetched {len(videos)} video(s) for channel {cid}. {'Updated' if changed else 'No change to'} {DATA.relative_to(ROOT)}.")
    write_output(changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
