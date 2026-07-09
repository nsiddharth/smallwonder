"""Daily news module: RSS feeds → local-model digest → Open WebUI knowledge.

Keeps the ensemble ambiently current without sending queries anywhere: the
only network traffic is fetching the feeds you configured, once a day. The
digest lands in a "Daily News" knowledge collection with a rolling window,
so chats can retrieve dated, cited briefs.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import feedparser
import httpx

from smallwonder.config import Config
from smallwonder.openwebui import OpenWebUI
from smallwonder.services import launchd

COLLECTION = "Daily News"
WINDOW_DAYS = 60
MAX_ITEMS_PER_FEED = 15

DIGEST_PROMPT = """You are writing a daily news brief for {date}. Below are raw \
headlines and summaries from RSS feeds. Produce a structured markdown brief:
group items by topic, 2-3 sentences per story, keep every source URL as a
markdown link, note anything time-sensitive. Skip duplicates and pure fluff.
Start with a 3-bullet "top of the day" section.

RAW ITEMS:
{items}"""


def install_timer(cfg: Config) -> None:
    launchd.install(
        "news",
        args=[sys.executable, "-m", "smallwonder.modules.news"],
        keep_alive=False,
        calendar={"hour": int(cfg.news.get("hour", 6)), "minute": 15},
    )


def fetch_items(cfg: Config) -> str:
    lines: list[str] = []
    for url in cfg.news.get("feeds", []):
        feed = feedparser.parse(url)
        source = feed.feed.get("title", url)
        for e in feed.entries[:MAX_ITEMS_PER_FEED]:
            title = e.get("title", "").strip()
            link = e.get("link", "")
            summary = (e.get("summary", "") or "")[:400]
            lines.append(f"- [{source}] {title} — {link}\n  {summary}")
    return "\n".join(lines)


def digest(cfg: Config, raw_items: str, date: str) -> str:
    r = httpx.post(
        f"{cfg.router_base}/v1/chat/completions",
        headers={"Authorization": f"Bearer {cfg.api_key}"},
        json={
            "model": "general",
            "messages": [
                {"role": "user", "content": DIGEST_PROMPT.format(date=date, items=raw_items)}
            ],
            "max_tokens": 6000,
            "reasoning_effort": "none",
        },
        timeout=600,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def prune_old(ui: OpenWebUI, knowledge_id: str) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=WINDOW_DAYS)
    removed = 0
    for f in ui.knowledge_files(knowledge_id):
        created = f.get("created_at")
        if created and datetime.fromtimestamp(created, tz=UTC) < cutoff:
            ui.remove_file_from_knowledge(knowledge_id, f["id"])
            removed += 1
    return removed


def run() -> None:
    cfg = Config.load()
    date = datetime.now().strftime("%Y-%m-%d")
    raw = fetch_items(cfg)
    if not raw.strip():
        print("no feed items fetched; skipping")
        return
    brief = digest(cfg, raw, date)
    ui = OpenWebUI(cfg)
    kid = ui.find_or_create_knowledge(
        COLLECTION, "Automated daily news briefs (smallwonder news module)"
    )
    file_id = ui.upload_text(f"news-{date}.md", f"# Daily brief — {date}\n\n{brief}")
    ui.add_file_to_knowledge(kid, file_id)
    pruned = prune_old(ui, kid)
    print(f"brief for {date} added to '{COLLECTION}' (pruned {pruned} old)")


if __name__ == "__main__":
    run()
