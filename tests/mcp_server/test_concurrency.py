import threading

from src.app import create_app
from src.config import Config
from src.models.task import Task


def test_concurrent_writes_through_the_endpoint_all_succeed(tmp_path):
    """
    Given the app on a real database file (as under waitress, one thread per request)
    When several threads capture tasks at once through the endpoint
    Then every call succeeds and every task gets its own ref
    """
    class FileConfig(Config):
        DATABASE_URL = f"sqlite:///{tmp_path / 'data.db'}"

    app = create_app(FileConfig)
    threads_count, per_thread = 8, 6
    failures = []

    def worker(number):
        client = app.test_client()
        for index in range(per_thread):
            body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "capture_task", "arguments": {"title": f"t{number}-{index}"}}}
            response = client.post("/mcp", json=body)
            result = (response.get_json() or {}).get("result", {})
            if response.status_code != 200 or result.get("isError"):
                failures.append((number, index, response.status_code, result))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    with app.app_context():
        stored = app.extensions["db_session"]().query(Task).all()
    assert len(stored) == threads_count * per_thread and len({t.ref for t in stored}) == len(stored)
