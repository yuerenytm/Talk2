from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from talk2.core.rag import chunk_markdown, index_library, search
from talk2.core.storage import Storage


SAMPLE = """# 拉萨旅行计划

## 第三天

上午去布达拉宫，下午在八廓街。
"""


def test_chunk_keeps_heading_path() -> None:
    pieces = chunk_markdown(SAMPLE)
    assert pieces
    assert any("拉萨旅行计划" in heading and "第三天" in heading for heading, _body in pieces)
    assert any("布达拉宫" in body for _heading, body in pieces)


def test_keyword_search_finds_note(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note_dir = vault / "旅行"
    note_dir.mkdir(parents=True)
    (note_dir / "拉萨.md").write_text(SAMPLE, encoding="utf-8")
    hidden = vault / ".obsidian"
    hidden.mkdir()
    (hidden / "隐藏.md").write_text("# 不该被索引\n密钥草稿\n", encoding="utf-8")

    store = Storage(tmp_path / "talk2.db")
    report = index_library(store, vault)
    assert report.files == 1
    assert report.chunks >= 1

    hits = search(store, vault, "拉萨旅行计划")
    assert hits
    assert hits[0].rel_path == "旅行/拉萨.md"
    assert "第三天" in hits[0].heading_path or "拉萨旅行计划" in hits[0].heading_path

    report_again = index_library(store, vault)
    assert report_again.files == 1

    (note_dir / "拉萨.md").write_text(SAMPLE + "\n补充：住在八廓街附近。\n", encoding="utf-8")
    index_library(store, vault)
    later = search(store, vault, "八廓街附近")
    assert any("八廓街附近" in hit.content for hit in later)


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    test_chunk_keeps_heading_path()
    with TemporaryDirectory() as folder:
        test_keyword_search_finds_note(Path(folder))
    print("rag ok")
