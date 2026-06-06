# AI RCA Allure resolver (`ai_rca/server_side`)

Allure attachments for SONiC-mgmt regression **Failure analysis** and **Cursor analysis prompt** are thin HTML stubs (~2 KB per test). The browser loads full UI and agent JSON from an HTTPS resolver server.

## Production vs local — which server does the demo use?

| Step | Where it runs | Uses which resolver? |
|------|---------------|----------------------|
| `pytest` demo | Your laptop / CI worker | **Does not** start a server |
| `allure serve` | Your laptop (browser) | **Production by default** |
| Attachment HTML fetch | Browser → `https://rm-via-allure.nvidia.com:9999` | **Production** |
| `/resolve` in demo mode | Browser → production with `demo=1` | **Production** (returns mock JSON) |

**Default demo commands hit the production server**, not a local process:

```bash

unset ALLURE_JSON_RESOLVER_SERVER_BASE  # that make sure this was not set to demo local server

python3 -m pytest ngts/scripts/ai_rca/demo/ \
  --confcutdir=ngts/scripts/ai_rca/demo \
  --alluredir=/tmp/allure-demo-agent-analysis -q

/tmp/allure-2.27.0/bin/allure serve /tmp/allure-demo-agent-analysis

```

- Pytest only writes small stub attachments into `/tmp/allure-demo-agent-analysis`.
- When you open **Failure analysis** / **Cursor analysis prompt** in the browser, JavaScript **fetches** HTML from **`https://rm-via-allure.nvidia.com:9999`**.
- Demo sets `ALLURE_ATTACHMENT_DEMO=1` → stubs pass `demo=1` → `/resolve?allure_url=http://demo/allure/local` returns **mock agent JSON** from the server (no real Allure URL or MISQL row needed).

To use a **local** resolver instead:

```bash
# Terminal 1 — local server (HTTP, mock data)
cd ngts/scripts/ai_rca/server_side
RESOLVE_DEV_HTTP=1 RESOLVE_MOCK=1 python3 -u allure_resolver_server.py

# Terminal 2 — demo pointing at localhost
export ALLURE_JSON_RESOLVER_SERVER_BASE=http://127.0.0.1:9999
python3 -m pytest ngts/scripts/ai_rca/demo/ \
  --confcutdir=ngts/scripts/ai_rca/demo \
  --alluredir=/tmp/allure-demo-agent-analysis -q
/tmp/allure-2.27.0/bin/allure serve /tmp/allure-demo-agent-analysis

```

---

## Demo steps (production server)

**Prerequisites:** production resolver running on `rm-via-allure.nvidia.com:9999`, DigiCert TLS under `/root/certification/`, network access from your browser.

### 1. Run demo pytest (from `sonic-mgmt` repo root)

```bash
cd sonic-mgmt

python3 -m pytest ngts/scripts/ai_rca/demo/ \
  --confcutdir=ngts/scripts/ai_rca/demo \
  --alluredir=/tmp/allure-demo-agent-analysis -q
```

### 2. Open Allure report

```bash
allure serve /tmp/allure-demo-agent-analysis
```

### 3. In the browser

1. Open test **`test_demo_allure_agent_analysis_attachments`**
2. Go to **Execution** → **Tear down**
3. Open **Failure analysis** — expect mock RCA sections + feedback buttons
4. Open **Cursor analysis prompt** — expect prompt text + copy button

### 4. Optional checks

```bash
# Resolver reachable (should return JSON with "ok": true)
curl -s "https://rm-via-allure.nvidia.com:9999/resolve?allure_url=http%3A%2F%2Fdemo%2Fallure%2Flocal" | head

# HTML attachment endpoint
curl -s "https://rm-via-allure.nvidia.com:9999/attachment/failure?demo=1" | head -5
```

If attachments stay on “Loading analysis from resolver…”, open the resolver URL in a new browser tab first (TLS trust), then reload the attachment.

---

## Deploy to production server

```bash
./ngts/scripts/ai_rca/server_side/deploy/sync_to_regression_server.sh
```

Target: `root@rm-via-allure.nvidia.com:/root/regression_ai_allure_attachment/src`

On the server:

```bash
cd /root/regression_ai_allure_attachment/src
./run_server_prod.sh
```

TLS defaults (see `deploy/ssl.env.example`):

- `/root/certification/new_rm_digicert.crt`
- `/root/certification/rm_allure_new.key`

---

## Project overview

### Problem

Allure HTML attachments for AI failure analysis used to embed ~160 KB of HTML + JS per test (templates, AllurClick2RM modal, agent formatting). That bloated Allure zips and slowed test runs.

### Solution

Split **client** (pytest) and **server** (resolver):

```
┌─────────────────────────────────────────────────────────────────────────┐
│  pytest workers (sonic-mgmt tests)                                      │
│  tests/common/plugins/allure_wrapper/ai_rca/                            │
│    per_test_analysis_attachment.py  → teardown hook                     │
│    analysis_attachments.py          → ~2 KB fetch stubs                 │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ Allure zip contains stubs only
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Browser (allure serve / allure.nvidia.com)                             │
│    1. Open attachment → stub fetch() resolver HTML                      │
│    2. Injected page → GET /resolve?allure_url=…                         │
│    3. Render agent JSON + RM bug modal + feedback                       │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTPS :9999
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ai_rca/server_side (ngts/scripts/ai_rca/server_side/)                  │
│    allure_resolver_server.py   — HTTPS API                              │
│    misql_pbi_connect.py        — Allure URL → agent JSON path (MISQL)   │
│    attachment_templates.py     — render failure_analysis / cursor HTML  │
│    embedded_rm_modal_loader.py — bundle AllurClick2RM JS                │
│    resolver_contract.py        — shared URLs/constants                  │
│    templates/*.html            — full UI                                │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
              ┌─────────────────┴─────────────────┐
              ▼                                   ▼
     MISQL / agent JSON on fit69          AllurClick2RM plugin_files
     (/auto/.../agent_output.json)        (bug report modal JS)
```

### Repository layout

| Path | Role |
|------|------|
| `ngts/scripts/ai_rca/demo/` | Standalone demo test (`--confcutdir`, not production) |
| `ngts/scripts/ai_rca/server_side/` | Resolver server, templates, deploy scripts |
| `ngts/scripts/AllurClick2RM/plugin_files/` | RM browser extension JS (embedded in Failure analysis) |
| `tests/common/plugins/allure_wrapper/ai_rca/` | Pytest plugin + `resolver_contract.py` (production client) |

### Resolver HTTP API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/resolve?allure_url=…` | Map Allure URL → agent JSON (MISQL); demo URL → mock JSON |
| `GET` | `/attachment/failure?…` | Full Failure analysis HTML |
| `GET` | `/attachment/cursor?…` | Full Cursor prompt HTML |
| `POST` | `/analysis_feedback` | Like/dislike + comment |

Default base URL: **`https://rm-via-allure.nvidia.com:9999`** (`resolver_contract.py`).

Override for workers or demo: `ALLURE_JSON_RESOLVER_SERVER_BASE`.

### Real regression runs

Pytest attaches the same stubs. In a real Allure report, the browser sends the **actual Allure page URL** to `/resolve`. The server looks up `allure_url_2test` in MISQL and returns agent output JSON. No `demo=1` unless `ALLURE_ATTACHMENT_DEMO=1`.

### Environment variables (common)

| Variable | Default | Used by |
|----------|---------|---------|
| `ALLURE_JSON_RESOLVER_SERVER_BASE` | `https://rm-via-allure.nvidia.com:9999` | Stubs + server |
| `ALLURE_ATTACHMENT_DEMO` | unset (demo sets `1`) | Adds `demo=1` to stub fetch URL |
| `RESOLVE_DEV_HTTP` | unset | Local server: HTTP instead of TLS |
| `RESOLVE_MOCK` | unset | Local server: mock all `/resolve` |
| `SSL_CERT_FILE` / `SSL_KEY_FILE` | `/root/certification/…` | Production TLS |
| `ALLURCLICK2RM_PLUGIN_DIR` | sibling `AllurClick2RM/plugin_files` | RM JS bundle path |
