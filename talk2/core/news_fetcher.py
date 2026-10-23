from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from html import unescape

DEFAULT_FEEDS = """https://feeds.bbci.co.uk/zhongwen/simp/rss.xml
https://feeds.bbci.co.uk/news/world/rss.xml
https://www.zaobao.com/rss/realtime/china
https://hnrss.org/frontpage
"""

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


@dataclass
class NewsItem:
    title: str
    summary: str
    source: str
    link: str


@dataclass
class Digest:
    items: list[NewsItem]
    summarized: bool
    raw_source_count: int
    model: str
    note: str

    def as_dict(self) -> dict:
        payload = asdict(self)
        return payload


def feed_urls(text: str) -> list[str]:
    urls = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def build_digest(#构建摘要
    feeds_text: str,
    complete: Callable[[list[dict[str, str]]], str] | None,
    model: str,
) -> Digest:
    urls = feed_urls(feeds_text) or feed_urls(DEFAULT_FEEDS)
    entries, source_count = collect_entries(urls)
    if not entries:
        return Digest([], False, 0, model, "这次没有取到新闻")
    raw = select_raw(entries, 10)
    if complete is None:
        return Digest(raw, False, source_count, model, "未摘要")
    try:
        text = complete(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _prompt_payload(entries)},
            ]
        )
        parsed = parse_items(text)
    except Exception:
        return Digest(raw, False, source_count, model, "未摘要")
    if not parsed:
        return Digest(raw, False, source_count, model, "未摘要")
    return Digest(_fill_to_ten(parsed, raw), True, source_count, model, "")


def collect_entries(urls: list[str]) -> tuple[list[NewsItem], int]:
    import feedparser

    entries: list[NewsItem] = []
    ok = 0
    for url in urls:
        try:
            payload = _download(url)
            parsed = feedparser.parse(payload)
        except Exception:
            continue
        source = ""
        feed = getattr(parsed, "feed", None)
        if feed is not None:
            source = str(getattr(feed, "title", "") or "")
        batch = []
        for entry in list(getattr(parsed, "entries", []))[:6]:
            title = _plain(str(getattr(entry, "title", "") or ""))
            if not title:
                continue
            summary = _plain(str(getattr(entry, "summary", "") or getattr(entry, "description", "") or ""))
            link = str(getattr(entry, "link", "") or "")
            batch.append(NewsItem(title, summary[:180], source or url, link))
        if batch:
            ok += 1
            entries.extend(batch)
    return entries, ok


def select_raw(entries: list[NewsItem], limit: int = 10) -> list[NewsItem]:#去重与截断
    seen: set[str] = set()
    chosen: list[NewsItem] = []
    for item in entries:
        key = item.link or item.title
        if key in seen:
            continue
        seen.add(key)
        chosen.append(item)
        if len(chosen) >= limit:
            break
    return chosen


def parse_items(text: str) -> list[NewsItem]:#解析JSON
    match = re.search(r"\[[\s\S]*\]", text or "")
    raw = match.group(0) if match else (text or "")
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("items") or data.get("news") or []
    items: list[NewsItem] = []
    if not isinstance(data, list):
        return []
    for row in data:
        if not isinstance(row, dict):
            continue
        title = _plain(str(row.get("title") or ""))
        if not title:
            continue
        items.append(
            NewsItem(
                title=title,
                summary=_plain(str(row.get("summary") or ""))[:200],
                source=_plain(str(row.get("source") or "")),
                link=str(row.get("link") or "").strip(),
            )
        )
        if len(items) >= 10:
            break
    return items


def _fill_to_ten(parsed: list[NewsItem], raw: list[NewsItem]) -> list[NewsItem]:#填充到10条
    if len(parsed) >= 10:
        return parsed[:10]
    seen = {item.link or item.title for item in parsed}
    filled = list(parsed)
    for item in raw:
        key = item.link or item.title
        if key in seen:
            continue
        filled.append(item)
        seen.add(key)
        if len(filled) >= 10:
            break
    return filled


def _plain(value: str) -> str:#清除HTML标签
    text = unescape(_TAG.sub(" ", value))
    return _SPACE.sub(" ", text).strip()


def _download(url: str, timeout: float = 12) -> bytes:#下载RSS
    import urllib.request

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Talk2/0.1 (news digest)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


_SYSTEM_PROMPT = (#系统提示词
    "你是新闻编辑。根据用户给出的 RSS 条目整理恰好 10 条简报。"
    "只输出 JSON 数组，不要输出其它文字。每项包含 title、summary、source、link。"
    "summary 用一两句中文说明。link 和事实必须来自输入，不要编造链接。"
    "条目不足 10 条时，按实际条数输出。"
)


def _prompt_payload(entries: list[NewsItem]) -> str:#提示词负载
    lines = []
    for index, item in enumerate(entries[:40], start=1):
        lines.append(
            f"{index}. 标题：{item.title}\n来源：{item.source}\n链接：{item.link}\n摘要：{item.summary}"
        )
    return "\n\n".join(lines)
