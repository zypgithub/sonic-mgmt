#!/usr/bin/env python3
"""
HTTPS server for AI regression RCA in Allure (pytest client stubs in ``tests/common/plugins/allure_wrapper/ai_rca/``).

Maps each Allure report URL to agent JSON via ``allure_agent_lookup.lookup_agent_by_allure_url``,
and records analysis Like/Dislike feedback.
Contract must match ``resolver_contract.ALLURE_JSON_RESOLVER_SERVER_BASE`` and ``ALLURE_JSON_RESOLVER_RESOLVE_PATH``:

* ``GET /resolve?allure_url=<url-encoded>`` — calls BI ``/allure-url-to-agent-full-path``,
  fetches agent output from fit69, then returns:
  ``{"ok": true, "path": "/auto/.../*_agent_output.json", "text": "...", "path_agent_input": "..."}``.
  Or ``{"ok": false, "reason": "agent_not_analyzed"}`` on miss (not cached).
  Successful lookups with a path are cached in memory per process.

* ``POST /analysis_feedback`` — Like/Dislike from the Allure HTML attachment (must match
  ``resolver_contract.ALLURE_ANALYSIS_FEEDBACK_PATH``).
  Body: ``application/x-www-form-urlencoded`` (preferred; avoids browser CORS preflight) or
  ``application/json``. Optional ``comment`` field (form key ``comment``) is stored with each vote.

  Persistence: merge into ``ALLURE_ANALYSIS_FEEDBACK_AGGREGATE_JSON`` (default
  ``/tmp/allure_analysis_feedback_by_url.json``) shaped as
  ``{ "<execution_id>": { "comment#1": {"vote":"like", ...}, ... } }``.
  Top-level keys are ``execution_id`` from agent output JSON when available; otherwise
  the normalized Allure URL (legacy fallback). Each entry also stores ``allure_url`` when sent.

* ``GET /attachment/failure?...`` / ``GET /attachment/cursor?...`` — full HTML for Allure stubs.

Local dev (fully offline resolver)::

    RESOLVE_DEV_HTTP=1 RESOLVE_MOCK=1 python3 ngts/scripts/ai_rca/server_side/allure_resolver_server.py

Demo against production: pytest demo sets ``ALLURE_ATTACHMENT_DEMO=1``; stubs fetch HTML from
``ALLURE_JSON_RESOLVER_SERVER_BASE`` with ``demo=1``. ``/resolve`` for ``http://demo/allure/local``
returns ``demo/fixtures/mock_agent_output.json`` without ``RESOLVE_MOCK``.

Debug why Allure shows "not exist" — extra ``/resolve`` lines **only** if ``RESOLVE_DEBUG`` is non-empty
(stderr; use ``python3 -u`` if lines appear late under systemd)::

    RESOLVE_DEBUG=1 python3 -u ngts/scripts/ai_rca/server_side/allure_resolver_server.py
"""
import json
import os
import re
import sys
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_AI_RCA_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _AI_RCA_DIR
for _ in range(8):
    if (_REPO_ROOT / "tests" / "common" / "plugins" / "allure_wrapper" / "ai_rca" / "resolver_contract.py").is_file():
        break
    parent = _REPO_ROOT.parent
    if parent == _REPO_ROOT:
        break
    _REPO_ROOT = parent
_TESTS_AI_RCA = _REPO_ROOT / "tests" / "common" / "plugins" / "allure_wrapper" / "ai_rca"
for _p in (_AI_RCA_DIR, _TESTS_AI_RCA):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from allure_agent_lookup import lookup_agent_by_allure_url, strip_fit69_url_prefix
import attachment_templates
from resolver_contract import (
    ALLURE_ATTACHMENT_CURSOR_PATH,
    ALLURE_ATTACHMENT_FAILURE_PATH,
    ALLURE_DEMO_ALLURE_URL,
)
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore


DEFAULT_PORT = 9999
SERVER_USER_AGENT = "AiRcaAllureServer/1.0"
DEFAULT_RESOLVE_FETCH_BASE = "http://fit69.mtl.labs.mlnx"
DEFAULT_SSL_CERT_FILE = "/root/certification/new_rm_digicert.crt"
DEFAULT_SSL_KEY_FILE = "/root/certification/rm_allure_new.key"

DEFAULT_ANALYSIS_FEEDBACK_PATH = "/analysis_feedback"
# In-memory cache: allure_url -> agent_full_path; only successful path lookups.
_RESOLVE_LOOKUP_CACHE: Dict[str, str] = {}
DEFAULT_ANALYSIS_FEEDBACK_AGGREGATE_JSON = "/tmp/allure_analysis_feedback_by_url.json"
FEEDBACK_BODY_MAX_BYTES = 262144
FEEDBACK_FIELD_MAX_LEN = 8192
RESOLVE_DEBUG_MAX_URL = 400


def _resolve_debug_enabled() -> bool:
    return bool((os.environ.get("RESOLVE_DEBUG") or "").strip())


def _resolve_debug(msg: str) -> None:
    """If ``RESOLVE_DEBUG`` is set, log one line to stderr (same stream as ``log_message``)."""
    if not _resolve_debug_enabled():
        return
    ts = datetime.now(timezone.utc).isoformat()
    sys.stderr.write("[resolve_debug %s] %s\n" % (ts, msg))
    try:
        sys.stderr.flush()
    except OSError:
        pass


def _server_feedback_http_path() -> str:
    """Route for POST feedback; must match ``resolver_contract.ALLURE_ANALYSIS_FEEDBACK_PATH``."""
    return DEFAULT_ANALYSIS_FEEDBACK_PATH.rstrip("/") or "/"


def _truncate_str(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len]


def _safe_auto_path(path: str) -> Optional[str]:
    p = unquote((path or "").strip())
    if not p.startswith("/auto/"):
        return None
    for seg in p.split("/"):
        if seg == "..":
            return None
    norm = os.path.normpath(p).replace("\\", "/")
    if not norm.startswith("/auto/"):
        return None
    return norm


def _paired_agent_input_path(resolved_path: str) -> Optional[str]:
    """If output file basename ends with ``agent_output.json``, return ``.../agent_input/model_input.json``."""
    rp = (resolved_path or "").strip().replace("\\", "/")
    if not rp or "/" not in rp:
        return None
    base = rp.rsplit("/", 1)[-1]
    if not base.endswith("agent_output.json"):
        return None
    parent = rp.rsplit("/", 1)[0]
    return parent + "/agent_input/model_input.json"


def _fetch_body_for_auto_path(safe_path: str) -> Tuple[bool, str, str]:
    """Return (ok, text, err). Prefer local file, else HTTP GET to FETCH_BASE + path."""
    if os.path.isfile(safe_path):
        with open(safe_path, "rb") as f:
            body = f.read()
        return True, body.decode("utf-8", errors="replace"), ""
    base = (
        os.environ.get("RESOLVE_MANUAL_FETCH_BASE") or DEFAULT_RESOLVE_FETCH_BASE
    ).strip().rstrip("/")
    target = base + safe_path
    try:
        req = Request(target, headers={"User-Agent": f"{SERVER_USER_AGENT} (resolve /auto path=)"})
        with urlopen(req, timeout=120) as resp:
            body = resp.read()
        return True, body.decode("utf-8", errors="replace"), ""
    except HTTPError as e:
        return False, "", f"upstream HTTP {e.code}"
    except URLError as e:
        return False, "", f"upstream error: {e.reason}"
    except OSError as e:
        return False, "", str(e)


def _resolve_auto_path(mapped: str) -> Tuple[Optional[str], str]:
    raw = strip_fit69_url_prefix((mapped or "").strip())
    if not raw:
        return None, "mapped_empty"
    safe = _safe_auto_path(raw)
    if safe:
        return safe, ""
    return None, "mapped_path_not_allowed"


def _mock_resolve_enabled() -> bool:
    return bool((os.environ.get("RESOLVE_MOCK") or "").strip())


def _is_demo_allure_url(allure_url):
    """Demo attachments use a fixed URL; production server returns mock JSON for it only."""
    u = (allure_url or "").strip().rstrip("/")
    return u == ALLURE_DEMO_ALLURE_URL.rstrip("/")


def _mock_agent_json_path() -> Path:
    override = (os.environ.get("RESOLVE_MOCK_AGENT_JSON") or "").strip()
    if override:
        return Path(override)
    return _AI_RCA_DIR / "demo" / "fixtures" / "mock_agent_output.json"


def _resolve_mock_response(allure_url: str) -> Dict[str, Any]:
    mock_auto_path = "/auto/demo/local/mock_agent_output.json"
    fp = _mock_agent_json_path()
    if fp.is_file():
        body = fp.read_text(encoding="utf-8")
    else:
        body = json.dumps({"execution_id": "mock-inline", "test_name": "mock_test", "data": {"root_cause_analysis": {"hypothesis": "inline mock"}}})
    out: Dict[str, Any] = {"ok": True, "path": mock_auto_path, "text": body}
    paired = _paired_agent_input_path(mock_auto_path)
    if paired:
        out["path_agent_input"] = paired
    return out


def _qs_first(qs: Dict[str, list], key: str, default: str = "") -> str:
    vals = qs.get(key, [])
    return vals[0] if vals else default


def _feedback_aggregate_path() -> str:
    return (
        os.environ.get("ALLURE_ANALYSIS_FEEDBACK_AGGREGATE_JSON") or ""
    ).strip() or DEFAULT_ANALYSIS_FEEDBACK_AGGREGATE_JSON


def _aggregate_file_lock(fh: Any, exclusive: bool) -> None:
    if fcntl is None:
        return
    op = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    fcntl.flock(fh.fileno(), op)


def _aggregate_file_unlock(fh: Any) -> None:
    if fcntl is None:
        return
    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _aggregate_next_comment_key(inner: Dict[str, Any]) -> str:
    mmax = 0
    for k in inner.keys():
        m = re.match(r"^comment#(\d+)$", str(k))
        if m:
            mmax = max(mmax, int(m.group(1)))
    return "comment#{}".format(mmax + 1)


def _allure_url_aggregate_key(allure_url: str) -> str:
    raw = (allure_url or "").strip()
    return _truncate_str(raw, min(FEEDBACK_FIELD_MAX_LEN, 4096)) or "_empty_url"


def _execution_id_from_agent_json_obj(obj: Any) -> str:
    """Read ``execution_id`` from agent output envelope or nested payload."""
    if not isinstance(obj, dict):
        return ""
    for key in ("execution_id", "executionId"):
        raw = obj.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    data = obj.get("data")
    if isinstance(data, dict):
        for key in ("execution_id", "executionId"):
            raw = data.get(key)
            if raw is not None and str(raw).strip():
                return str(raw).strip()
    return ""


def _execution_id_from_agent_output_file(agent_output_path: str) -> str:
    safe = _safe_auto_path(agent_output_path)
    if not safe or not os.path.isfile(safe):
        return ""
    try:
        with open(safe, encoding="utf-8") as fh:
            obj = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return ""
    return _execution_id_from_agent_json_obj(obj)


def _feedback_aggregate_key(execution_id: str, allure_url: str) -> str:
    """Prefer MARS ``execution_id``; fall back to Allure URL when absent."""
    eid = (execution_id or "").strip()
    if eid:
        return _truncate_str(eid, min(FEEDBACK_FIELD_MAX_LEN, 4096))
    return _allure_url_aggregate_key(allure_url)


def _merge_feedback_aggregate(
    execution_id: str,
    allure_url: str,
    vote: str,
    comment: Optional[str],
    extras: Dict[str, Any],
) -> Tuple[bool, str, str]:
    """
    Merge one vote+comment into a JSON object keyed by execution_id (or Allure URL fallback).
    Returns (ok, error_message_or_empty, new_comment_key).
    """
    path = _feedback_aggregate_path()
    agg_key = _feedback_aggregate_key(execution_id, allure_url)
    srv_ts = datetime.now(timezone.utc).isoformat()
    comment_clean: Optional[str] = (comment or "").strip() or None
    entry: Dict[str, Any] = {
        "vote": vote,
        "comment": comment_clean,
        "server_received_ts": srv_ts,
    }
    url_clean = (allure_url or "").strip()
    if url_clean:
        entry["allure_url"] = _truncate_str(url_clean, min(FEEDBACK_FIELD_MAX_LEN, 4096))
    for ek in (
        "setup_name",
        "session_id",
        "test_nodeid",
        "client_ts",
        "agent_output_path",
    ):
        v = extras.get(ek)
        if v is not None and str(v).strip():
            entry[ek] = _truncate_str(str(v), FEEDBACK_FIELD_MAX_LEN)

    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent, mode=0o755, exist_ok=True)
        except OSError as e:
            return False, str(e), ""

    ck = ""
    try:
        with open(path, "a+", encoding="utf-8") as fh:
            _aggregate_file_lock(fh, True)
            try:
                fh.seek(0)
                blob = fh.read()
                root: Dict[str, Any]
                if blob.strip():
                    try:
                        parsed_root = json.loads(blob)
                        root = parsed_root if isinstance(parsed_root, dict) else {}
                    except json.JSONDecodeError:
                        root = {}
                else:
                    root = {}
                inner = root.get(agg_key)
                if not isinstance(inner, dict):
                    inner = {}
                ck = _aggregate_next_comment_key(inner)
                inner[ck] = entry
                root[agg_key] = inner
                out = json.dumps(root, ensure_ascii=False, indent=2)
                fh.seek(0)
                fh.truncate(0)
                fh.write(out)
                fh.flush()
            finally:
                _aggregate_file_unlock(fh)
    except OSError as e:
        return False, str(e), ""
    return True, "", ck


def _resolve_agent_path_for_allure_url(allure_url: str) -> Tuple[Optional[str], str]:
    """Return (agent_full_path, reason). ``agent_full_path`` is ``None`` on miss (reason set)."""
    target_raw = (allure_url or "").strip()
    if not target_raw:
        return None, "invalid_allure_url"

    if target_raw in _RESOLVE_LOOKUP_CACHE:
        cached_path = _RESOLVE_LOOKUP_CACHE[target_raw]
        _resolve_debug("lookup cache HIT url=%r path=%r" % (target_raw[:RESOLVE_DEBUG_MAX_URL], cached_path))
        return cached_path, ""

    try:
        agent_path = lookup_agent_by_allure_url(target_raw)
    except Exception as e:
        return None, f"lookup_error:{e}"

    if not agent_path:
        _resolve_debug("lookup cache SKIP (no path) url=%r" % target_raw[:RESOLVE_DEBUG_MAX_URL])
        return None, "agent_not_analyzed"

    _RESOLVE_LOOKUP_CACHE[target_raw] = agent_path
    _resolve_debug(
        "lookup cache STORE url=%r (cache_size=%d)"
        % (target_raw[:RESOLVE_DEBUG_MAX_URL], len(_RESOLVE_LOOKUP_CACHE))
    )
    return agent_path, ""


def _cors_headers(handler: BaseHTTPRequestHandler) -> Dict[str, str]:
    origin = handler.headers.get("Origin")
    h: Dict[str, str] = {}
    if origin:
        h["Access-Control-Allow-Origin"] = origin
        h["Access-Control-Allow-Credentials"] = "true"
    else:
        h["Access-Control-Allow-Origin"] = "*"
    h["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    h["Access-Control-Allow-Headers"] = "Content-Type"
    return h


class AiRcaAllureHandler(BaseHTTPRequestHandler):
    server_version = SERVER_USER_AGENT

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        for k, v in _cors_headers(self).items():
            self.send_header(k, v)
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        fb_path = _server_feedback_http_path().rstrip("/") or "/"
        if path != fb_path:
            self.send_response(404)
            for k, v in _cors_headers(self).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b"not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"ok": False, "error": "invalid Content-Length"})
            return
        if length > FEEDBACK_BODY_MAX_BYTES:
            self._json(413, {"ok": False, "error": "body too large"})
            return
        raw = self.rfile.read(length) if length > 0 else b""
        ct_header = self.headers.get("Content-Type") or ""
        ct_main = ct_header.split(";")[0].strip().lower()
        data: Dict[str, Any]
        if ct_main == "application/x-www-form-urlencoded":
            try:
                body_s = raw.decode("utf-8")
            except UnicodeDecodeError:
                self._json(400, {"ok": False, "error": "invalid body encoding"})
                return
            data = {k: (v[0] if v else "") for k, v in parse_qs(body_s, keep_blank_values=True).items()}
        else:
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json(
                    400,
                    {
                        "ok": False,
                        "error": "invalid JSON (or send application/x-www-form-urlencoded from browser)",
                    },
                )
                return
            if not isinstance(parsed, dict):
                self._json(400, {"ok": False, "error": "JSON body must be an object"})
                return
            data = parsed

        vote = str(data.get("vote") or "").strip().lower()
        if vote not in ("like", "dislike"):
            self._json(400, {"ok": False, "error": 'vote must be "like" or "dislike"'})
            return

        m = FEEDBACK_FIELD_MAX_LEN
        raw_url = str(data.get("allure_url") or "")
        execution_id = str(data.get("execution_id") or data.get("executionId") or "").strip()
        comment_raw = _truncate_str(str(data.get("comment") or "").strip(), m)
        extras = {
            "setup_name": str(data.get("setup_name") or ""),
            "session_id": str(data.get("session_id") or ""),
            "test_nodeid": str(data.get("test_nodeid") or ""),
            "client_ts": str(data.get("client_ts") or ""),
            "agent_output_path": str(data.get("agent_output_path") or ""),
        }
        if not execution_id:
            execution_id = _execution_id_from_agent_output_file(extras.get("agent_output_path") or "")
        ok_agg, err_agg, ckey = _merge_feedback_aggregate(
            execution_id, raw_url, vote, comment_raw, extras
        )
        if not ok_agg:
            self._json(500, {"ok": False, "error": "failed to update feedback aggregate", "detail": err_agg})
            return
        self._json(
            200,
            {
                "ok": True,
                "aggregate_file": _feedback_aggregate_path(),
                "comment_key": ckey,
                "aggregate_key": _feedback_aggregate_key(execution_id, raw_url),
            },
        )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        if path == "/resolve":
            allure_urls = qs.get("allure_url", [])
            allure_url = allure_urls[0] if allure_urls else ""
            if not allure_url:
                self._json(400, {"ok": False, "error": "missing allure_url query parameter"})
                return
            _resolve_debug(
                "resolve start client=%s allure_url=%r"
                % (
                    self.client_address[0],
                    allure_url[:RESOLVE_DEBUG_MAX_URL] +
                    ("…" if len(allure_url) > RESOLVE_DEBUG_MAX_URL else ""),
                )
            )
            if _mock_resolve_enabled() or _is_demo_allure_url(allure_url):
                self._json(200, _resolve_mock_response(allure_url))
                return
            mapped_path, reason = _resolve_agent_path_for_allure_url(allure_url)
            _resolve_debug("lookup -> mapped_path=%r reason=%r" % (mapped_path, reason))
            if not mapped_path:
                out_err: Dict[str, Any] = {"ok": False, "reason": reason or "agent_not_analyzed"}
                if reason == "agent_not_analyzed":
                    out_err["message"] = (
                        "Sorry, the agent still didn't analyze this failure."
                    )
                self._json(200, out_err)
                return
            safe, mapped_reason = _resolve_auto_path(mapped_path)
            _resolve_debug("auto_path -> safe=%r mapped_reason=%r" % (safe, mapped_reason))
            if not safe:
                self._json(200, {"ok": False, "reason": mapped_reason, "path": mapped_path})
                return
            ok, text, err = _fetch_body_for_auto_path(safe)
            resolved_path = safe
            _resolve_debug(
                "fetch -> ok=%s resolved_path=%r err=%r text_len=%s"
                % (ok, resolved_path, err, len(text) if ok and text else 0)
            )
            if not ok:
                self._json(200, {"ok": False, "reason": "read_error", "path": resolved_path, "error": err})
                return
            out: Dict[str, Any] = {"ok": True, "path": resolved_path, "text": text}
            paired_input = _paired_agent_input_path(resolved_path)
            if paired_input:
                out["path_agent_input"] = paired_input
            _resolve_debug(
                "resolve success text_len=%s keys=%s"
                % (len(text or ""), list(out.keys()))
            )
            self._json(200, out)
            return

        if path == ALLURE_ATTACHMENT_FAILURE_PATH:
            body = attachment_templates.render_failure_analysis_html(
                title=_qs_first(qs, "title", "Failure analysis"),
                setup_name=_qs_first(qs, "setup_name"),
                session_id=_qs_first(qs, "session_id"),
                test_nodeid=_qs_first(qs, "test_nodeid"),
                demo=_qs_first(qs, "demo") == "1",
            )
            self._html(200, body)
            return

        if path == ALLURE_ATTACHMENT_CURSOR_PATH:
            body = attachment_templates.render_cursor_prompt_html(
                title=_qs_first(qs, "title", "Cursor analysis prompt"),
                test_nodeid=_qs_first(qs, "test_nodeid"),
                probe_test_name=_qs_first(qs, "probe_test_name"),
                demo=_qs_first(qs, "demo") == "1",
            )
            self._html(200, body)
            return

        self.send_response(404)
        for k, v in _cors_headers(self).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b"not found")

    def _html(self, code: int, body: str) -> None:
        raw = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        for k, v in _cors_headers(self).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _json(self, code: int, obj: object) -> None:
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        for k, v in _cors_headers(self).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _ssl_cert_paths() -> Tuple[str, str]:
    """TLS paths: ``SSL_CERT_FILE`` / ``SSL_KEY_FILE`` env, else production defaults."""
    cert = (os.environ.get("SSL_CERT_FILE") or DEFAULT_SSL_CERT_FILE).strip()
    key = (os.environ.get("SSL_KEY_FILE") or DEFAULT_SSL_KEY_FILE).strip()
    return cert, key


def main() -> None:
    port = int(os.environ.get("PORT", str(DEFAULT_PORT)))
    bind = os.environ.get("BIND", "0.0.0.0")
    dev_http = bool((os.environ.get("RESOLVE_DEV_HTTP") or "").strip())
    if dev_http and not (os.environ.get("ALLURE_JSON_RESOLVER_SERVER_BASE") or "").strip():
        os.environ["ALLURE_JSON_RESOLVER_SERVER_BASE"] = f"http://127.0.0.1:{port}"
    httpd = HTTPServer((bind, port), AiRcaAllureHandler)
    fb_route = _server_feedback_http_path()
    fb_agg = _feedback_aggregate_path()
    if dev_http:
        print(
            f"ai_rca allure_resolver_server: http://127.0.0.1:{port}/ "
            f"(GET /resolve, GET {ALLURE_ATTACHMENT_FAILURE_PATH}, GET {ALLURE_ATTACHMENT_CURSOR_PATH}, "
            f"POST {fb_route} -> {fb_agg}) [RESOLVE_DEV_HTTP]",
            file=sys.stderr,
        )
        if _mock_resolve_enabled():
            print(f"RESOLVE_MOCK=1 fixture={_mock_agent_json_path()}", file=sys.stderr)
    else:
        ssl_cert_file, ssl_key_file = _ssl_cert_paths()
        if not os.path.isfile(ssl_cert_file):
            raise RuntimeError(f"TLS certificate not found: {ssl_cert_file}")
        if not os.path.isfile(ssl_key_file):
            raise RuntimeError(f"TLS private key not found: {ssl_key_file}")
        tls_proto = getattr(ssl, "PROTOCOL_TLS_SERVER", ssl.PROTOCOL_SSLv23)
        ctx = ssl.SSLContext(tls_proto)
        ctx.load_cert_chain(certfile=ssl_cert_file, keyfile=ssl_key_file)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        print(
            f"ai_rca allure_resolver_server: https://127.0.0.1:{port}/ "
            f"(GET /resolve, GET {ALLURE_ATTACHMENT_FAILURE_PATH}, GET {ALLURE_ATTACHMENT_CURSOR_PATH}, "
            f"POST {fb_route} -> {fb_agg}) bind {bind}:{port}",
            file=sys.stderr,
        )
        print(f"TLS cert={ssl_cert_file} key={ssl_key_file}", file=sys.stderr)
    print("Stop with Ctrl+C", file=sys.stderr)
    if _resolve_debug_enabled():
        print(
            "RESOLVE_DEBUG is on: each GET /resolve will print [resolve_debug …] lines to stderr.",
            file=sys.stderr,
            flush=True,
        )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
