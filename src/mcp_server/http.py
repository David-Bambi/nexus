import logging
from importlib import metadata
from urllib.parse import urlsplit

from flask import Blueprint, current_app, jsonify, request

from src.mcp_server import tools

logger = logging.getLogger(__name__)

# The MCP endpoint. Adapters only, like the web pages: check the request,
# call the tool layer, shape the JSON-RPC reply.
bp = Blueprint("mcp", __name__)

# Protocol versions this server speaks, newest first.
PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]

# Hostnames the endpoint answers to. Anything else (a DNS-rebinding page, a
# forwarded name) is refused: the app has no authentication and must only be
# reachable as itself on loopback.
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

# Largest request body accepted, in bytes.
MAX_BODY = 1_000_000

# What the assistant is told about the server when it connects.
INSTRUCTIONS = (
    "Nexus is a GTD-style project manager: projects contain versions, versions contain tasks. "
    "Identify projects by key, tasks by ref (t-…) and versions by ref (v-…) or by number within a project. "
    "Tasks move inbox -> refined -> planned -> doing -> waiting/done. "
    "Use dry_run with import_data before importing for real."
)

# JSON-RPC error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


def _app_version() -> str:
    """The installed application version, or "unknown" when not installed."""
    try:
        return metadata.version("nexus")
    except metadata.PackageNotFoundError:
        return "unknown"


def _rpc_result(request_id : object, result : dict):
    """A JSON-RPC success reply."""
    return jsonify({"jsonrpc": "2.0", "id": request_id, "result": result})


def _rpc_error(request_id : object, code : int, message : str, status : int = 200):
    """A JSON-RPC error reply, with the given HTTP status."""
    response = jsonify({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})
    response.status_code = status
    return response


def _refused(status : int, reason : str):
    """A refusal made before the body is looked at."""
    logger.warning("MCP request refused (%s): %s", status, reason)
    return reason, status, {"Content-Type": "text/plain; charset=utf-8"}


def _guard():
    """Refuse requests a browser page or a rebinding attack could make.

    Runs before anything is parsed or executed.

    Returns:
        A refusal response, or None if the request may proceed.
    """
    host = urlsplit(f"//{request.host}").hostname
    if host not in LOOPBACK_HOSTS:
        return _refused(421, "unexpected Host")

    # Only browsers send Origin, and only same-origin pages may drive the
    # endpoint: the Origin must be exactly this server's own address.
    origin = request.headers.get("Origin")
    if origin is not None and urlsplit(origin).netloc.lower() != request.host.lower():
        return _refused(403, "cross-origin request refused")

    # A form or a simple cross-site request can't send this type without a
    # preflight, which this server never grants.
    if request.mimetype != "application/json":
        return _refused(415, "Content-Type must be application/json")

    version = request.headers.get("MCP-Protocol-Version")
    if version is not None and version not in PROTOCOL_VERSIONS:
        return _refused(400, f"unsupported MCP-Protocol-Version {version!r}")
    return None


def _initialize(request_id : object, params : dict):
    """Answer the handshake, agreeing on a protocol version."""
    asked = params.get("protocolVersion")
    return _rpc_result(request_id, {
        "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "nexus", "version": _app_version()},
        "instructions": INSTRUCTIONS,
    })


def _call_tool(request_id : object, params : dict):
    """Run a tool and reply with its result."""
    name, arguments = params.get("name"), params.get("arguments")
    if not isinstance(name, str):
        return _rpc_error(request_id, INVALID_PARAMS, "'name' must be a string")

    session = current_app.extensions["db_session"]()
    try:
        result = tools.call_tool(session, name, arguments)
    except tools.UnknownTool:
        return _rpc_error(request_id, INVALID_PARAMS, f"Unknown tool: {name}")
    except Exception:
        # A bug or a database failure: keep the assistant informed instead of
        # answering with an HTML error page, and keep the detail in the log.
        logger.exception("MCP tool %s failed", name)
        result = tools.failure("internal error, see the server log")
    logger.info("MCP tool %s: %s", name, "error" if result["isError"] else "ok")
    return _rpc_result(request_id, result)


@bp.post("/mcp")
def endpoint():
    """Serve one JSON-RPC message: a request gets a reply, a notification gets 202.

    Stateless: no session, no streaming, one POST and one JSON reply.
    """
    refusal = _guard()
    if refusal is not None:
        return refusal

    request.max_content_length = MAX_BODY
    message = request.get_json(silent=True)
    if message is None:
        return _rpc_error(None, PARSE_ERROR, "invalid JSON", 400)
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _rpc_error(None, INVALID_REQUEST, "expected a single JSON-RPC 2.0 message", 400)

    # A notification, or a reply to the server (which never asks anything).
    if "id" not in message or "method" not in message:
        return "", 202

    request_id, method = message["id"], message["method"]
    params = message.get("params") or {}
    if not isinstance(method, str) or not isinstance(params, dict):
        return _rpc_error(request_id, INVALID_REQUEST, "malformed request")

    if method == "initialize":
        return _initialize(request_id, params)
    if method == "ping":
        return _rpc_result(request_id, {})
    if method == "tools/list":
        return _rpc_result(request_id, {"tools": tools.list_tools()})
    if method == "tools/call":
        return _call_tool(request_id, params)
    return _rpc_error(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")
