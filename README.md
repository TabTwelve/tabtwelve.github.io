# tabtwelve.com

The Tab Twelve website. A small static site: latest episode, catalogue, one page per episode with sources, About, Privacy. Every video plays on YouTube.

## How it stays up to date

Nothing to do after uploading a video. A GitHub Action runs every hour, reads the channel's public RSS feed, and rebuilds the site if there is anything new. It also runs on every push to `main`.

## Layout

| Path | What it is |
|---|---|
| `site.config.json` | Name, tagline, domain, socials, contact email, switches for newsletter, shop and analytics |
| `data/videos.json` | The channel's videos, written by the Action (don't edit by hand) |
| `content/episodes/*.md` | Optional notes and sources for an episode, matched to a video by `video_id` |
| `templates/` | Page templates (Jinja2) |
| `static/` | CSS, images, favicon, robots.txt, CNAME. Copied to the site root as is |
| `scripts/fetch_videos.py` | Pulls the YouTube feed into `data/videos.json` |
| `scripts/build.py` | Renders everything into `dist/` |
| `.github/workflows/deploy.yml` | Hourly fetch, build and deploy to GitHub Pages |

## Adding sources and notes for an episode

1. Copy an existing file in `content/episodes/` and name it after the episode.
2. Set `video_id` to the YouTube video id (the part after `watch?v=`). While it says `TBD` the page is skipped.
3. Write the notes in Markdown below the front matter.

Pages appear at `/episodes/<slug>/`. The slug comes from `slug:` in the front matter, or from the video title if there isn't one.

## Building locally

```
pip install -r requirements.txt
python scripts/fetch_videos.py   # optional, needs internet
python scripts/build.py
python -m http.server -d dist 8000
```

## Switches in `site.config.json`

- `newsletter.enabled` plus `newsletter.form_action`: turns on the email signup section.
- `shop.enabled` and `shop.url`: adds Shop to the navigation.
- `analytics.cloudflare_token`: adds cookie-free Cloudflare Web Analytics.
- `hide_video_ids`: video ids to leave off the site.
