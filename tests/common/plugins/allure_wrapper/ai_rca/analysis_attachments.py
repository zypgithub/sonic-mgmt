"""
Allure HTML attachment stubs (pytest client).

Full HTML is served by ``ngts/scripts/ai_rca/server_side/`` at
``GET {BASE}/attachment/failure?...`` and ``GET {BASE}/attachment/cursor?...``.
"""
import html
import json
import os
from urllib.parse import urlencode

from tests.common.plugins.allure_wrapper.ai_rca.resolver_contract import (
    ALLURE_ATTACHMENT_CURSOR_PATH,
    ALLURE_ATTACHMENT_FAILURE_PATH,
    ALLURE_BUG_REPORT_POST_DEFAULT,
    ALLURE_DEMO_ALLURE_URL,
    ALLURE_JSON_RESOLVER_RESOLVE_PATH,
    ALLURE_JSON_RESOLVER_SERVER_BASE,
    ALLURE_ANALYSIS_FEEDBACK_PATH,
    _resolver_base_for_attach,
    cursor_prompt_session_storage_key,
    get_bug_report_post_url,
    get_feedback_path,
    get_resolver_server_base,
    resolver_result_session_storage_key,
)

# Re-export contract symbols for existing imports.
__all__ = [
    "ALLURE_ANALYSIS_FEEDBACK_PATH",
    "ALLURE_ATTACHMENT_CURSOR_PATH",
    "ALLURE_ATTACHMENT_FAILURE_PATH",
    "ALLURE_BUG_REPORT_POST_DEFAULT",
    "ALLURE_DEMO_ALLURE_URL",
    "ALLURE_JSON_RESOLVER_RESOLVE_PATH",
    "ALLURE_JSON_RESOLVER_SERVER_BASE",
    "attach_cursor_prompt_html",
    "attach_json_resolved_by_allure_url",
    "cursor_prompt_session_storage_key",
    "get_bug_report_post_url",
    "get_feedback_path",
    "get_resolver_server_base",
    "resolver_result_session_storage_key",
]


def _build_server_attachment_fetch_stub(server_path, params, compact=False):
    base = _resolver_base_for_attach()
    clean = {k: v for k, v in params.items() if v is not None and str(v).strip()}
    if (os.environ.get("ALLURE_ATTACHMENT_DEMO") or "").strip():
        clean["demo"] = "1"
    qs = urlencode(clean)
    fetch_url = "{}{}{}".format(base, server_path, "?" + qs if qs else "")
    js_url = json.dumps(fetch_url)
    title = html.escape(params.get("title", "Analysis"), quote=True)
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8"/>'
        f"<title>{title}</title>\n"
        "<style>html,body{margin:0;padding:0;min-height:0;font:15px/1.5 system-ui,sans-serif}"
        ".err,.load{padding:12px}.err{color:#cf222e}.load{color:#444}</style></head>\n"
        '<body><div class="load" id="boot">Loading analysis from resolver…</div>\n'
        "<script>\n(function(){\n"
        f"  var url={js_url};\n"
        "  function measureContentHeight(){\n"
        "    var best=0;\n"
        "    var nodes=document.body?document.body.children:[];\n"
        "    for(var i=0;i<nodes.length;i++){\n"
        "      var el=nodes[i];\n"
        "      if(!el||el.nodeType!==1)continue;\n"
        "      if(el.id==='fa-overlay-trigger-fab'||el.id==='cursor-copy-fab')continue;\n"
        "      if(el.offsetParent===null&&el.style&&el.style.display==='none')continue;\n"
        "      var r=el.getBoundingClientRect();\n"
        "      if(r.height<=0)continue;\n"
        "      best=Math.max(best,r.bottom+window.pageYOffset);\n"
        "    }\n"
        "    if(best<24)best=Math.max(document.body.scrollHeight||0,document.documentElement.scrollHeight||0,24);\n"
        "    return Math.ceil(best+10);\n"
        "  }\n"
        "  function computeFrameHeight(){\n"
        "    var contentH=measureContentHeight();\n"
        "    try{\n"
        "      if(window.__sonicMgmtPreferredHeight){\n"
        "        var pref=window.__sonicMgmtPreferredHeight(contentH);\n"
        "        if(pref&&pref>0)return Math.ceil(pref);\n"
        "      }\n"
        "    }catch(ePref){}\n"
        "    return contentH;\n"
        "  }\n"
        "  function shrinkWrap(){\n"
        "    try{\n"
        "      document.documentElement.style.height='auto';\n"
        "      document.body.style.height='auto';\n"
        "      document.documentElement.style.minHeight='0';\n"
        "      document.body.style.minHeight='0';\n"
        "      var h=computeFrameHeight();\n"
        "      var fe=window.frameElement;\n"
        "      if(fe){\n"
        "        fe.style.height=h+'px';fe.style.minHeight=h+'px';fe.style.maxHeight='none';fe.style.overflow='auto';\n"
        "        var p=fe.parentElement;\n"
        "        while(p){\n"
        "          p.style.height=h+'px';p.style.minHeight='0';p.style.maxHeight='none';p.style.overflow='visible';\n"
        "          if(p.classList&&(p.classList.contains('attachment')||p.classList.contains('attachment__content')))break;\n"
        "          p=p.parentElement;\n"
        "        }\n"
        "      }\n"
        "    }catch(e){}\n"
        "  }\n"
        "  function scheduleShrinkWrap(){\n"
        "    shrinkWrap();setTimeout(shrinkWrap,100);setTimeout(shrinkWrap,400);setTimeout(shrinkWrap,1200);\n"
        "  }\n"
        "  window.__sonicMgmtShrinkWrap=shrinkWrap;\n"
        "  window.scheduleShrinkWrap=scheduleShrinkWrap;\n"
        "  function injectHtml(html){\n"
        "    var doc=new DOMParser().parseFromString(html,'text/html');\n"
        "    document.title=doc.title||document.title;\n"
        "    document.head.innerHTML='';\n"
        "    var hs=doc.head.querySelectorAll('style,link[rel=stylesheet]');\n"
        "    for(var i=0;i<hs.length;i++)document.head.appendChild(hs[i].cloneNode(true));\n"
        "    document.body.innerHTML=doc.body.innerHTML;\n"
        "    var scripts=doc.body.querySelectorAll('script');\n"
        "    function runScript(idx){\n"
        "      if(idx>=scripts.length){scheduleShrinkWrap();return;}\n"
        "      var old=scripts[idx],neu=document.createElement('script');\n"
        "      if(old.src){neu.src=old.src;neu.onload=function(){runScript(idx+1);};neu.onerror=function(){runScript(idx+1);};}\n"
        "      else{neu.textContent=old.textContent;}\n"
        "      document.body.appendChild(neu);\n"
        "      if(!old.src)runScript(idx+1);\n"
        "    }\n"
        "    runScript(0);\n"
        "  }\n"
        "  var ctrl=typeof AbortController!=='undefined'?new AbortController():null;\n"
        "  var timer=setTimeout(function(){if(ctrl)ctrl.abort();},20000);\n"
        '  fetch(url,{credentials:"omit",signal:ctrl?ctrl.signal:undefined})\n'
        "    .then(function(r){clearTimeout(timer);if(!r.ok)throw new Error('HTTP '+r.status);return r.text();})\n"
        "    .then(injectHtml)\n"
        "    .catch(function(e){clearTimeout(timer);var msg=(e&&e.name==='AbortError')?'timed out after 20s':String(e);document.body.innerHTML='<div class=\"err\">Could not load from resolver ('+msg+'). Open '+url.split('?')[0]+' in a new browser tab first (accept TLS cert if prompted), then reload this attachment. Resolver: "
        + html.escape(_resolver_base_for_attach(), quote=True)
        + ".</div>';shrinkWrap();});\n"
        "})();\n</script></body></html>"
    )


def attach_cursor_prompt_html(test_nodeid, probe_test_name="", *, name="Cursor analysis prompt"):
    import allure

    doc = _build_server_attachment_fetch_stub(
        ALLURE_ATTACHMENT_CURSOR_PATH,
        {"test_nodeid": (test_nodeid or "").strip(), "probe_test_name": (probe_test_name or "").strip(), "title": name},
        compact=True,
    )
    allure.attach(doc.encode("utf-8"), name=name, attachment_type=allure.attachment_type.HTML, extension="html")


def attach_json_resolved_by_allure_url(
    name="Agent Failure analysis",
    *,
    setup_name=None,
    session_id=None,
    test_nodeid=None,
):
    import allure

    doc = _build_server_attachment_fetch_stub(
        ALLURE_ATTACHMENT_FAILURE_PATH,
        {
            "setup_name": (setup_name or "").strip(),
            "session_id": (session_id or "").strip(),
            "test_nodeid": (test_nodeid or "").strip(),
            "title": name,
        },
    )
    allure.attach(doc.encode("utf-8"), name=name, attachment_type=allure.attachment_type.HTML, extension="html")
