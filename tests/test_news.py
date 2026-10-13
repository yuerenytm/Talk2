from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from talk2.core.news_fetcher import NewsItem, parse_items, select_raw
from talk2.core.platform import launch_spec, linux_desktop_text
from talk2.core.scheduler import should_fire


def test_should_fire_once_per_day() -> None:
    morning = datetime(2026, 10, 13, 8, 5)
    assert should_fire(True, "08:00", "", morning)
    assert not should_fire(True, "08:00", "2026-10-13", morning)
    assert not should_fire(True, "09:00", "", datetime(2026, 10, 13, 8, 5))
    assert not should_fire(False, "08:00", "", morning)


def test_parse_items_and_raw_limit() -> None:
    text = '说明\n[{"title": "拉萨", "summary": "第三天", "source": "BBC", "link": "https://example.com/a"}]'
    items = parse_items(text)
    assert items[0].title == "拉萨"
    assert items[0].link == "https://example.com/a"
    raw = select_raw(
        [
            NewsItem("一", "", "源", "https://a"),
            NewsItem("一重复", "", "源", "https://a"),
            NewsItem("二", "", "源", "https://b"),
        ],
        limit=10,
    )
    assert [item.title for item in raw] == ["一", "二"]


def test_linux_desktop_entry() -> None:
    text = linux_desktop_text("/usr/bin/python3", Path("/home/me/Talk2"))
    assert "Exec=/usr/bin/python3 -m talk2" in text
    assert "Path=/home/me/Talk2" in text
    frozen = linux_desktop_text("/opt/Talk2/Talk2", Path("/opt/Talk2"), [])
    assert "Exec=/opt/Talk2/Talk2\n" in frozen
    assert "-m talk2" not in frozen


def test_launch_spec() -> None:
    exe, args, workdir = launch_spec(frozen=False)
    assert args == ["-m", "talk2"]
    assert workdir.name
    packaged, packaged_args, packaged_dir = launch_spec(frozen=True)
    assert packaged_args == []
    assert packaged_dir == Path(packaged).parent
    assert exe


if __name__ == "__main__":
    test_should_fire_once_per_day()
    test_parse_items_and_raw_limit()
    test_linux_desktop_entry()
    test_launch_spec()
    print("news ok")
