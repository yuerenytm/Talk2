from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from talk2.core.storage import Storage


def test_conversation_roundtrip(tmp_path: Path) -> None:
    store = Storage(tmp_path / 'talk2.db')
    conv = store.create_conversation('测试')
    store.add_message(conv.id, 'user', '你好')
    store.add_message(conv.id, 'assistant', '你好，有什么可以帮忙的？')
    messages = store.list_messages(conv.id)
    assert [m.role for m in messages] == ['user', 'assistant']
    assert store.chat_payload(conv.id)[0]['content'] == '你好'
    store.set_setting('model', 'demo')
    assert store.get_setting('model') == 'demo'
    store.delete_conversation(conv.id)
    assert store.list_conversations() == []


if __name__ == '__main__':
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as folder:
        test_conversation_roundtrip(Path(folder))
    print('storage ok')
