"""
Load AllurClick2RM browser scripts for embedding in the Failure analysis Allure HTML attachment.

Repo layout::

    ngts/scripts/
      ai_rca/server_side/
        embedded_rm_modal_loader.py
        embedded_rm_modal/failure_analysis_bridge.js
      AllurClick2RM/plugin_files/*.js

Production deploy (flat) copies plugin_files next to the server under ``AllurClick2RM/plugin_files/``.
"""
import os
from pathlib import Path

_WRAPPER_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _WRAPPER_DIR.parent.parent
_REPO_PLUGIN_DIR = _SCRIPTS_DIR / "AllurClick2RM" / "plugin_files"
_FLAT_PLUGIN_DIR = _WRAPPER_DIR / "AllurClick2RM" / "plugin_files"
_BRIDGE_PATH = _WRAPPER_DIR / "embedded_rm_modal" / "failure_analysis_bridge.js"


def _plugin_dir():
    override = (os.environ.get("ALLURCLICK2RM_PLUGIN_DIR") or "").strip()
    if override:
        return Path(override)
    if _FLAT_PLUGIN_DIR.is_dir():
        return _FLAT_PLUGIN_DIR
    if _REPO_PLUGIN_DIR.is_dir():
        return _REPO_PLUGIN_DIR
    return _FLAT_PLUGIN_DIR


def _read_plugin_file(name):
    path = _plugin_dir() / name
    if not path.is_file():
        raise FileNotFoundError(
            "AllurClick2RM plugin file missing for embedded modal: {} "
            "(set ALLURCLICK2RM_PLUGIN_DIR or deploy AllurClick2RM/plugin_files)".format(path)
        )
    return path.read_text(encoding="utf-8")


def build_rm_modal_bundle_js():
    parts = [
        _read_plugin_file("RichTextEditor.js"),
        _read_plugin_file("BugDraftStorage.js"),
        _read_plugin_file("BugReportUI.js"),
        _read_plugin_file("UsernameManager.js"),
        _read_plugin_file("BugDataCollector.js"),
        _read_plugin_file("Sender.js"),
        _BRIDGE_PATH.read_text(encoding="utf-8"),
    ]
    return "\n;\n".join(parts)


def escape_for_inline_script(js):
    return js.replace("</script>", "<\\/script>")
