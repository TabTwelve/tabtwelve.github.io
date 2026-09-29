#!/usr/bin/env python3
"""Build the static site into dist/.

Inputs
  site.config.json        site-wide settings (name, domain, socials, toggles)
  data/videos.json        the channel's videos, written by fetch_videos.py
  content/episodes/*.md   optional notes and sources per episode, matched by video_id
  templates/*.html        Jinja2 templates
  static/                 copied to dist/ as is

Run:  python scripts/build.py
"""
import html
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
CONFIG = json.loads((ROOT / "site.config.json").read_text(encoding="utf-8"))

TIMESTAMP_RE = re.compile(r"^\s*(\d{1,2}:)?\d{1,2}:\d{2}\s+(.+?)\s*$")
URL_RE = re.compile(r"(https?://[^\s<>\"']+)")


# ---------- helpers ----------

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:80] or "episode"


def parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Tiny front matter parser: `key: value` lines between --- fences."""
    meta: dict = {}
    body = raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"').strip("'")
            body = parts[2]
    return meta, body.strip()


def fmt_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return f"{dt.day} {dt.strftime('%B %Y')}"


def timestamp_seconds(ts: str) -> int:
    parts = [int(p) for p in ts.split(":")]
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return secs


def split_description(desc: str) -> tuple[str, list[dict], str]:
    """Return (summary, chapters, rest) from a YouTube description."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", desc.strip()) if p.strip()]
    summary = paragraphs[0] if paragraphs else ""
    chapters: list[dict] = []
    rest_paras: list[str] = []
    for p in paragraphs[1:]:
        lines = p.splitlines()
        stamped = [ln for ln in lines if re.match(r"^\s*(\d{1,2}:)?\d{1,2}:\d{2}\s+\S", ln)]
        if stamped and len(stamped) >= max(2, len(lines) - 1):
            for ln in stamped:
                m = re.match(r"^\s*((?:\d{1,2}:)?\d{1,2}:\d{2})\s+(.+?)\s*$", ln)
                if m:
                    chapters.append({"time": m.group(1), "seconds": timestamp_seconds(m.group(1)), "title": m.group(2)})
        else:
            rest_paras.append(p)
    return summary, chapters, "\n\n".join(rest_paras)


def linkify(text: str) -> str:
    """Escape text, turn URLs into links and newlines into <br>."""
    out = []
    pos = 0
    for m in URL_RE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        url = m.group(1).rstrip(".,)")
        trail = m.group(1)[len(url):]
        out.append(f'<a href="{html.escape(url)}" rel="noopener" target="_blank">{html.escape(url)}</a>{html.escape(trail)}')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    s = "".join(out)
    paras = [p for p in re.split(r"\n\s*\n", s) if p.strip()]
    return "".join("<p>" + p.replace("\n", "<br>") + "</p>" for p in paras)


def md(text: str) -> str:
    return markdown.markdown(text, extensions=["sane_lists", "smarty"], output_format="html5")


# ---------- load content ----------

def load_videos() -> list[dict]:
    path = ROOT / "data" / "videos.json"
    if not path.exists():
        return []
    videos = json.loads(path.read_text(encoding="utf-8"))
    hidden = set(CONFIG.get("hide_video_ids", []))
    return [v for v in videos if v.get("id") not in hidden]


def load_notes() -> dict[str, dict]:
    notes: dict[str, dict] = {}
    for path in sorted((ROOT / "content" / "episodes").glob("*.md")):
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        vid = (meta.get("video_id") or "").strip()
        if not vid or vid.upper() == "TBD":
            continue  # not published yet; page appears once the id is filled in
        notes[vid] = {"meta": meta, "body": body, "file": path.name}
    return notes


def build_episodes(videos: list[dict], notes: dict[str, dict]) -> list[dict]:
    episodes = []
    used_slugs: set[str] = set()
    total = len(videos)
    for i, v in enumerate(videos):
        note = notes.get(v["id"], {})
        meta = note.get("meta", {})
        slug = meta.get("slug") or slugify(v["title"])
        if slug in used_slugs:
            slug = f"{slug}-{v['id'][:6].lower()}"
        used_slugs.add(slug)
        summary, chapters, rest = split_description(v.get("description", ""))
        number = meta.get("episode")
        if not number:
            number = total - i  # oldest video is episode 1
        ep = {
            "id": v["id"],
            "title": meta.get("title") or v["title"],
            "slug": slug,
            "url": f"/episodes/{slug}/",
            "youtube_url": f"https://www.youtube.com/watch?v={v['id']}",
            "published": v.get("published", ""),
            "date": fmt_date(v.get("published", "")),
            "thumb": f"https://i.ytimg.com/vi/{v['id']}/maxresdefault.jpg",
            "thumb_fallback": f"https://i.ytimg.com/vi/{v['id']}/hqdefault.jpg",
            "summary": meta.get("summary") or summary,
            "chapters": chapters,
            "description_html": linkify(rest) if rest else "",
            "notes_html": md(note["body"]) if note.get("body") else "",
            "number": int(number) if str(number).isdigit() else number,
        }
        episodes.append(ep)
    return episodes


# ---------- render ----------

def main() -> int:
    env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    videos = load_videos()
    notes = load_notes()
    episodes = build_episodes(videos, notes)
    latest = episodes[0] if episodes else None

    site = dict(CONFIG)
    site["youtube_url"] = f"https://www.youtube.com/@{CONFIG['youtube']['handle']}"
    site["subscribe_url"] = site["youtube_url"] + "?sub_confirmation=1"
    site["year"] = datetime.now(timezone.utc).year
    site["built_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    shutil.copytree(ROOT / "static", DIST, dirs_exist_ok=True)

    pages: list[tuple[str, str, dict]] = [
        ("index.html", "index.html", {"latest": latest, "episodes": episodes[: CONFIG.get("episodes_on_home", 12)], "total": len(episodes)}),
        ("episodes/index.html", "episodes.html", {"episodes": episodes}),
        ("about/index.html", "about.html", {}),
        ("privacy/index.html", "privacy.html", {}),
        ("404.html", "404.html", {}),
    ]
    for ep in episodes:
        pages.append((f"episodes/{ep['slug']}/index.html", "episode.html", {"ep": ep}))

    urls = []
    for out_path, template_name, ctx in pages:
        tpl = env.get_template(template_name)
        path_part = "/" if out_path == "index.html" else "/" + out_path.replace("index.html", "")
        page_url = site["base_url"] + path_part
        html_out = tpl.render(site=site, page_url=page_url, **ctx)
        target = DIST / out_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html_out, encoding="utf-8")
        if out_path != "404.html":
            urls.append(page_url)

    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"  <url><loc>{html.escape(u)}</loc></url>" for u in urls]
    sitemap.append("</urlset>")
    (DIST / "sitemap.xml").write_text("\n".join(sitemap) + "\n", encoding="utf-8")

    print(f"Built {len(pages)} page(s) with {len(episodes)} episode(s) into {DIST.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
