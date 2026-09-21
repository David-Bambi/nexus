import json

import pytest

from src.mcp_server.http import MAX_BODY, PROTOCOL_VERSIONS
from src.models.task import Task


def rpc(client, method, params=None, request_id=1, **kwargs):
    """POST a JSON-RPC request to the endpoint."""
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return client.post("/mcp", json=message, **kwargs)


def call(client, name, arguments=None, **kwargs):
    """Call a tool over the endpoint and return the JSON-RPC result."""
    body = rpc(client, "tools/call", {"name": name, "arguments": arguments or {}}, **kwargs).get_json()
    return body["result"]


def task_count(app):
    """Number of tasks in the database."""
    with app.app_context():
        return app.extensions["db_session"]().query(Task).count()


# Protocol ------------------------------------------------------------------------------------------

def test_initialize_agrees_on_a_version_and_describes_the_server(client):
    """
    Given a client asking for a supported protocol version
    When it initializes
    Then the version is echoed and the server describes itself and its tools capability
    """
    result = rpc(client, "initialize", {"protocolVersion": "2025-06-18"}).get_json()["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["serverInfo"]["name"] == "nexus" and "tools" in result["capabilities"]
    assert "Nexus" in result["instructions"]


def test_initialize_falls_back_to_the_latest_version(client):
    """
    Given a client asking for an unknown protocol version
    When it initializes
    Then the server answers with its newest version
    """
    result = rpc(client, "initialize", {"protocolVersion": "1999-01-01"}).get_json()["result"]
    assert result["protocolVersion"] == PROTOCOL_VERSIONS[0]


def test_ping_and_tools_list(client):
    """
    Given the endpoint
    When pinging and listing tools
    Then ping is empty and every tool comes with its schema and annotations
    """
    assert rpc(client, "ping").get_json() == {"jsonrpc": "2.0", "id": 1, "result": {}}
    listed = rpc(client, "tools/list").get_json()["result"]["tools"]
    assert len(listed) == 20 and {"name", "description", "inputSchema", "annotations"} <= set(listed[0])


def test_notifications_and_client_replies_get_202_and_no_body(client):
    """
    Given a notification and a JSON-RPC reply from the client
    When posting them
    Then each is acknowledged with 202 and an empty body
    """
    for message in ({"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 7, "result": {}}):
        response = client.post("/mcp", json=message)
        assert (response.status_code, response.data) == (202, b"")


def test_request_ids_are_echoed(client):
    """
    Given string and integer ids
    When posting requests
    Then each reply carries its id
    """
    assert rpc(client, "ping", request_id="abc").get_json()["id"] == "abc"
    assert rpc(client, "ping", request_id=42).get_json()["id"] == 42


@pytest.mark.parametrize("body,status,code", [
    (b"{nope", 400, -32700),
    (b"[]", 400, -32600),
    (b'[{"jsonrpc": "2.0", "id": 1, "method": "ping"}]', 400, -32600),
    (b'{"id": 1, "method": "ping"}', 400, -32600),
    (b'"text"', 400, -32600),
])
def test_malformed_messages_are_rejected(client, body, status, code):
    """
    Given unparsable, batched or non JSON-RPC bodies
    When posting them
    Then they get a JSON-RPC error and the matching HTTP status
    """
    response = client.post("/mcp", data=body, content_type="application/json")
    assert response.status_code == status and response.get_json()["error"]["code"] == code


@pytest.mark.parametrize("message,code", [
    ({"jsonrpc": "2.0", "id": 1, "method": "resources/list"}, -32601),
    ({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": [1]}, -32600),
    ({"jsonrpc": "2.0", "id": 1, "method": 5}, -32600),
    ({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}}, -32602),
    ({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "nope"}}, -32602),
])
def test_bad_methods_and_params_are_json_rpc_errors(client, message, code):
    """
    Given an unknown method, malformed params, or an unknown tool
    When posting them
    Then a JSON-RPC error with the right code comes back
    """
    assert client.post("/mcp", json=message).get_json()["error"]["code"] == code


# Tools over HTTP -----------------------------------------------------------------------------------

def test_tool_calls_round_trip_and_persist(client, app):
    """
    Given the endpoint
    When capturing a task then listing tasks through tools/call
    Then the task is stored and comes back with its ref
    """
    captured = call(client, "capture_task", {"title": "Over HTTP"})
    assert captured["isError"] is False and captured["structuredContent"]["ref"].startswith("t-")
    listed = call(client, "list_tasks")["structuredContent"]["tasks"]
    assert [t["title"] for t in listed] == ["Over HTTP"] and task_count(app) == 1


def test_tool_refusals_are_results_not_http_errors(client):
    """
    Given a call the tool refuses
    When posting it
    Then the HTTP status is 200 and the result is flagged as an error with the message
    """
    response = rpc(client, "tools/call", {"name": "get_task", "arguments": {"ref": "t-zzz"}})
    result = response.get_json()["result"]
    assert response.status_code == 200 and result["isError"] is True and "doesn't exist" in result["content"][0]["text"]


def test_non_ascii_survives_the_round_trip(client):
    """
    Given a title with accents
    When capturing and reading it back
    Then it is unchanged
    """
    call(client, "capture_task", {"title": "Améliorer le visuel"})
    assert call(client, "inbox")["structuredContent"]["tasks"][0]["title"] == "Améliorer le visuel"


# Guard ---------------------------------------------------------------------------------------------

CAPTURE = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
           "params": {"name": "capture_task", "arguments": {"title": "Should not exist"}}}


@pytest.mark.parametrize("base_url", ["http://127.0.0.1:8765", "http://localhost:8765", "http://[::1]:8765", "http://localhost"])
def test_loopback_hosts_are_served(client, base_url):
    """
    Given any spelling of the loopback address
    When posting to the endpoint
    Then it answers
    """
    assert client.post("/mcp", json=CAPTURE, base_url=base_url).status_code == 200


@pytest.mark.parametrize("base_url", ["http://evil.example", "http://localhost.evil.example:8765",
                                      "http://127.0.0.1.evil.example", "http://192.168.1.5:8765", "http://0.0.0.0:8765"])
def test_foreign_hosts_are_refused_and_nothing_runs(client, app, base_url):
    """
    Given a Host that is not loopback (DNS rebinding, LAN name)
    When posting a write
    Then it is refused with 421 and nothing is written
    """
    response = client.post("/mcp", json=CAPTURE, base_url=base_url)
    assert response.status_code == 421 and task_count(app) == 0


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://localhost:3000", "http://127.0.0.1:9999",
                                    "http://localhost:8765.evil.example"])
def test_cross_origin_requests_are_refused_and_nothing_runs(client, app, origin):
    """
    Given a browser page on another origin, even another local port
    When it posts a write
    Then it is refused with 403 and nothing is written
    """
    response = client.post("/mcp", json=CAPTURE, base_url="http://127.0.0.1:8765", headers={"Origin": origin})
    assert response.status_code == 403 and task_count(app) == 0


def test_same_origin_is_served(client, app):
    """
    Given a page served by the app itself
    When it posts with its own origin
    Then the call runs
    """
    response = client.post("/mcp", json=CAPTURE, base_url="http://127.0.0.1:8765",
                           headers={"Origin": "http://127.0.0.1:8765"})
    assert response.status_code == 200 and task_count(app) == 1


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data"])
def test_non_json_content_types_are_refused(client, app, content_type):
    """
    Given a body sent with a content type a cross-site form can produce
    When posting it
    Then it is refused with 415 and nothing is written
    """
    response = client.post("/mcp", data=json.dumps(CAPTURE), content_type=content_type)
    assert response.status_code == 415 and task_count(app) == 0


def test_missing_content_type_is_refused(client):
    """
    Given a post without a content type
    When posting it
    Then it is refused with 415
    """
    assert client.post("/mcp", data=json.dumps(CAPTURE)).status_code == 415


def test_guard_runs_before_the_body_is_read(client):
    """
    Given a foreign host and a body that is not even JSON
    When posting it
    Then the host is refused first
    """
    response = client.post("/mcp", data=b"{nope", content_type="application/json", base_url="http://evil.example")
    assert response.status_code == 421


def test_unsupported_protocol_version_header_is_refused(client):
    """
    Given an MCP-Protocol-Version this server doesn't speak
    When posting
    Then it is refused with 400; a supported one is served
    """
    assert client.post("/mcp", json=CAPTURE, headers={"MCP-Protocol-Version": "1999-01-01"}).status_code == 400
    assert client.post("/mcp", json=CAPTURE, headers={"MCP-Protocol-Version": PROTOCOL_VERSIONS[0]}).status_code == 200


def test_oversized_bodies_are_refused(client, app):
    """
    Given a body over the limit
    When posting it
    Then it is refused with 413 and nothing is written
    """
    huge = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "capture_task", "arguments": {"title": "x" * (MAX_BODY + 10)}}}
    assert client.post("/mcp", json=huge).status_code == 413 and task_count(app) == 0


def test_only_post_is_allowed_and_no_cors_is_granted(client):
    """
    Given the endpoint
    When using other methods or a preflight
    Then they are refused or answered without any CORS permission
    """
    for method in ("get", "put", "delete", "patch", "head"):
        assert getattr(client, method)("/mcp").status_code == 405
    preflight = client.options("/mcp", headers={"Origin": "https://evil.example",
                                                "Access-Control-Request-Method": "POST"})
    assert not any(h.lower().startswith("access-control-allow") for h in preflight.headers.keys())


def test_unexpected_tool_failure_is_a_readable_error_result_and_is_logged(client, app, monkeypatch, caplog):
    """
    Given a tool failing with an unexpected exception
    When calling it over HTTP
    Then the assistant gets an error result (not an HTML 500) and the traceback is logged
    """
    from src.mcp_server import tools

    def boom(session, args):
        raise RuntimeError("secret detail")

    monkeypatch.setitem(tools.TOOLS, "inbox", tools.Tool("inbox", "", tools.TOOLS["inbox"].schema, boom, read_only=True))
    response = rpc(client, "tools/call", {"name": "inbox", "arguments": {}})
    result = response.get_json()["result"]
    assert response.status_code == 200 and result["isError"] is True
    assert "internal error" in result["content"][0]["text"] and "secret detail" not in json.dumps(result)
    assert "secret detail" in caplog.text
