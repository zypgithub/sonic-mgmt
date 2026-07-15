"""
Low-perturbation bgpd instrumentation for sonic-net/sonic-buildimage#27787
([bgp][allow_list] soft-inbound clear monopolizes bgpd CPU -> hold-timer expiry).

Captures a bundle of signals around the allow-list soft clear so that WHEN the
flaky flap reproduces we can pin it to the outbound subgroup_announce_table walk
starving keepalives. Artifacts are preserved ONLY when a flap is detected (or when
force_preserve=True, for the fire-drill self-test), and a generate_dump plugin folds
the preserved bundle into the techsupport/sysdump automatically (no-op on clean runs).

Signals (all DUT-side, all wrapped so instrumentation never fails the test):
  A) FRR 'debug bgp update-groups' -> dedicated /var/log/frr/bgp_dbg.log.
  B) event_cpu snapshot before/after -> which scheduler events ate CPU in the window.
  C) top -H on bgpd -> proves the single main thread was pinned ~100% during the block.
  D) perf -F 99 --call-graph -> where inside the announce walk the time went (if perf present).
  E) flap detection via Hold-Timer-Expired delta + established-count delta.
  F) bgpd_state.txt + full bgpd.log -> running-config, summaries, update-groups, neighbors.

Intentionally KEPT OFF: 'debug bgp updates/keepalives/bestpath' -- observer effect.
"""
import base64
import logging
import time

logger = logging.getLogger(__name__)

CAP_SECS = 90
DBG_FILE = "/var/log/frr/bgp_dbg.log"
ART = "/tmp/bgp27787"
PRESERVE = "/var/log/bgp27787"
PLUGIN = "/usr/local/bin/debug-dump/bgp27787-bundle"

# generate_dump plugin: prints the preserved flap bundle (quick-read text + whole-bundle
# base64 tar.gz) into the techsupport tarball, but only if a flap was preserved this run.
_PLUGIN_SRC = r"""#!/bin/bash
set +e
BDIR=/var/log/bgp27787
PRES=$(ls -dt "$BDIR"/PRESERVED_* 2>/dev/null | head -1)
[ -z "$PRES" ] && exit 0
echo "########## sonic-net/sonic-buildimage#27787 FLAP BUNDLE ($PRES) ##########"
for f in VERDICT.txt bgpd_state.txt bgpcfgd_window.log bgpd_window.log holdexpiry.log \
         bgp_dbg.log ev.before ev.after bgpd_threads.log perf.log; do
  [ -f "$PRES/$f" ] && { echo; echo "===== $f ====="; cat "$PRES/$f"; }
done
echo; echo "===== FULL BUNDLE (base64 tar.gz of $(basename "$PRES"); recover: base64 -d | tar xzf -) ====="
tar czf - -C "$(dirname "$PRES")" "$(basename "$PRES")" 2>/dev/null | base64
"""


def _sh(duthost, cmd):
    return duthost.shell(cmd, module_ignore_errors=True)


def _out(res):
    try:
        return res.get("stdout", "").strip()
    except Exception:
        return ""


def _hte_count(duthost):
    # count REAL bgpd hold-timer notifications only: anchor on the bgp#bgpd[PID]: tag and drop
    # ansible/sudo self-echoes (our own greps get logged to syslog and would otherwise self-match).
    r = _sh(duthost, "sudo grep -aE 'bgp#bgpd\\[[0-9]+\\]:.*Hold Timer Expired' /var/log/syslog 2>/dev/null "
                     "| grep -avE 'ansible|_raw_params|COMMAND=' | wc -l")
    try:
        return int(_out(r) or "0")
    except ValueError:
        return 0


def _established(duthost, af):
    cmd = ('docker exec bgp vtysh -c "show {af} bgp summary json" 2>/dev/null | '
           'python3 -c "import sys,json;'
           'k=\'ipv4Unicast\' if \'{af}\'==\'ip\' else \'ipv6Unicast\';'
           'p=json.load(sys.stdin).get(k,{{}}).get(\'peers\',{{}});'
           'print(sum(1 for v in p.values() if v.get(\'state\')==\'Established\'))"').format(af=af)
    try:
        return int(_out(_sh(duthost, cmd)) or "0")
    except ValueError:
        return -1


def _install_dump_plugin(duthost):
    b64 = base64.b64encode(_PLUGIN_SRC.encode()).decode()
    _sh(duthost, "sudo mkdir -p /usr/local/bin/debug-dump")
    _sh(duthost, "echo %s | base64 -d | sudo tee %s >/dev/null && sudo chmod 755 %s"
        % (b64, PLUGIN, PLUGIN))


def _snapshot_bgpd_state(duthost):
    """F) comprehensive bgpd state -> bgpd_state.txt + full bgpd.log."""
    st = "%s/bgpd_state.txt" % ART
    _sh(duthost, "sudo rm -f %s" % st)
    for vc in ["show running-config bgpd", "show ip bgp summary", "show bgp ipv6 summary",
               "show bgp update-groups", "show bgp update-groups summary", "show bgp ipv6 neighbors"]:
        _sh(duthost, "echo '===== %s =====' | sudo tee -a %s >/dev/null && "
                     "sudo docker exec bgp vtysh -c '%s' 2>/dev/null | sudo tee -a %s >/dev/null"
                     % (vc, st, vc, st))
    # full bgpd log: FRR file if present + REAL bgpd daemon lines from syslog (anchored on bgp#bgpd[PID]:,
    # excluding our own ansible/sudo grep echoes). NOTE: bgp_dbg.log is the authoritative window trace
    # (start_capture points FRR's file log at it at 'debugging' level, so it captures ALL bgpd messages).
    _sh(duthost, "( sudo docker exec bgp cat /var/log/frr/bgpd.log 2>/dev/null; "
                 "sudo grep -aE 'bgp#bgpd\\[[0-9]+\\]:' /var/log/syslog 2>/dev/null | grep -avE 'ansible|_raw_params|COMMAND=' ) "
                 "| sudo tee %s/bgpd_full.log >/dev/null || true" % ART)


def start_capture(duthost):
    """Enable update-groups debug + start perf/top/event_cpu capture. Returns ctx dict."""
    ctx = {"t0": _out(_sh(duthost, "date +%s"))}
    _sh(duthost, "mkdir -p %s" % ART)
    # clean only STALE preserved bundles (>2h old); keep sibling parametrized-run bundles intact
    _sh(duthost, "sudo find %s -maxdepth 1 -name 'PRESERVED_*' -mmin +120 -exec rm -rf {} + 2>/dev/null; "
                 "sudo mkdir -p %s" % (PRESERVE, PRESERVE))
    _install_dump_plugin(duthost)
    _sh(duthost, 'docker exec bgp vtysh -c "conf t" -c "log file %s debugging"' % DBG_FILE)
    _sh(duthost, 'docker exec bgp vtysh -c "debug bgp update-groups"')
    _sh(duthost, 'docker exec bgp vtysh -c "show event cpu" > %s/ev.before 2>/dev/null' % ART)
    ctx["hte0"] = _hte_count(duthost)
    _v4, _v6 = _established(duthost, "ip"), _established(duthost, "ipv6")
    ctx["estab0"] = "v4=%d v6=%d" % (_v4, _v6)
    ctx["estab_n"] = max(_v4, 0) + max(_v6, 0)
    _sh(duthost, "sudo nohup top -H -b -d1 -n %d -p $(pidof bgpd) > %s/bgpd_threads.log 2>&1 &"
        % (CAP_SECS, ART))
    _sh(duthost,
        "if command -v perf >/dev/null 2>&1; then sudo rm -f %s/bgpd.perf; "
        "sudo nohup perf record -F 99 --call-graph dwarf -p $(pidof bgpd) "
        "-o %s/bgpd.perf -- sleep %d > %s/perf.log 2>&1 & fi" % (ART, ART, CAP_SECS, ART))
    time.sleep(1)
    logger.info("bgp27787: capture started T0=%s baseline %s HTE=%d",
                ctx["t0"], ctx["estab0"], ctx["hte0"])
    return ctx


def collect_and_restore(duthost, ctx, label, force_preserve=False):
    """Snapshot event_cpu AFTER, restore debug, detect flap, preserve+fold-into-dump on failure.
    force_preserve=True forces the preserve path (used by the fire-drill self-test)."""
    try:
        _sh(duthost, "sudo pkill -INT -f 'perf record.*bgpd.perf' 2>/dev/null; sleep 2")
        _sh(duthost, 'docker exec bgp vtysh -c "show event cpu" > %s/ev.after 2>/dev/null' % ART)
        _sh(duthost, "sudo docker exec bgp cat %s > %s/bgp_dbg.log 2>/dev/null || : " % (DBG_FILE, ART))
        _snapshot_bgpd_state(duthost)
        _sh(duthost, "sudo grep -aE 'bgp#bgpd\\[[0-9]+\\]:.*(Hold Timer Expired|ADJCHANGE)' /var/log/syslog 2>/dev/null "
                     "| grep -avE 'ansible|_raw_params|COMMAND=' | tail -200 > %s/holdexpiry.log" % ART)
        _sh(duthost, "( sudo docker exec bgp sh -c 'tail -300 /var/log/frr/bgpd.log 2>/dev/null'; "
                     "sudo grep -aE 'bgp#bgpd\\[[0-9]+\\]:' /var/log/syslog 2>/dev/null | grep -avE 'ansible|_raw_params|COMMAND=' | tail -300 ) "
                     "> %s/bgpd_window.log 2>/dev/null" % ART)
        _sh(duthost, "sudo grep -aE 'clear bgp peer-group|restart bgp peer-group' "
                     "/var/log/syslog 2>/dev/null | tail -40 > %s/bgpcfgd_window.log" % ART)
        hte1 = _hte_count(duthost)
        _v4, _v6 = _established(duthost, "ip"), _established(duthost, "ipv6")
        estab1 = "v4=%d v6=%d" % (_v4, _v6)
        estab1_n = max(_v4, 0) + max(_v6, 0)
        dropped = estab1_n < ctx.get("estab_n", estab1_n)     # sessions DROPPED = real flap
        hte_flap = hte1 > ctx.get("hte0", 0)                  # real bgpd hold-timer notifications increased
        flapped = force_preserve or dropped or hte_flap
        why = "test-failure" if force_preserve else ("estab-drop" if dropped else ("hte" if hte_flap else "-"))
        summary = ("bgp27787[%s]: HTE %d->%d  estab %s->%s  reason=%s => %s"
                   % (label, ctx.get("hte0", 0), hte1, ctx.get("estab0"), estab1, why,
                      "PRESERVE" if flapped else "clean"))
        _sh(duthost, "echo '%s' > %s/VERDICT.txt" % (summary, ART))
        if flapped:
            logger.warning(summary)
            dst = "%s/PRESERVED_%s" % (PRESERVE, label)
            _sh(duthost, "sudo mkdir -p %s && sudo cp -f %s/* %s/ 2>/dev/null" % (dst, ART, dst))
            logger.warning("bgp27787: artifacts PRESERVED at %s (auto-folded into sysdump via %s)", dst, PLUGIN)
        else:
            logger.info(summary)
            _sh(duthost, "sudo rm -f %s/bgpd.perf 2>/dev/null" % ART)
    finally:
        _sh(duthost, 'docker exec bgp vtysh -c "no debug bgp update-groups" 2>/dev/null')
        _sh(duthost, 'docker exec bgp vtysh -c "conf t" -c "no log file %s" 2>/dev/null' % DBG_FILE)
        _sh(duthost, "sudo pkill -f 'perf record.*bgpd.perf' 2>/dev/null; "
                     "sudo pkill -f 'top -H -b .* -p' 2>/dev/null; true")
