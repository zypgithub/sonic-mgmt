/**
 * Runs in the same window/document as the Allure Failure analysis attachment (or top window).
 * Depends on globals from AllurClick2RM (loaded first):
 *   RichTextEditor, BugReportUI, UsernameManager, BugDataCollector, BugReportSender
 *
 * Reuses AllurClick2RM ``plugin_files`` (UI + POST). Iframe vs ``window.top`` handling lives in this
 * bridge so ``plugin_files/*.js`` stay unchanged. On OK: merge flat payload (same shape as
 * ``BugDataCollector.prepareBugReportData``) and POST via ``BugReportSender``.
 */
(function () {
  "use strict";

  /** Same key as ``UsernameManager`` in ``UsernameManager.js`` (localStorage + cookie name). */
  var BUG_PLUGIN_USERNAME_KEY = "bug_plugin_username";
  /** Same-tab fallback when storage is blocked or partitioned (Allure iframe). */
  var USERNAME_MEM_PROP = "__sonicMgmtBugReporterUsername";

  /** iframe (attachment) and ``window.top`` (Allure report) — RM bundle may run on either. */
  function storageRoots() {
    var roots = [];
    function add(w) {
      if (!w) {
        return;
      }
      for (var j = 0; j < roots.length; j++) {
        if (roots[j] === w) {
          return;
        }
      }
      roots.push(w);
    }
    add(window);
    try {
      add(window.top);
    } catch (e1) {}
    return roots;
  }

  function readUsernameFromMemory() {
    try {
      if (window.top && window.top[USERNAME_MEM_PROP]) {
        var a = String(window.top[USERNAME_MEM_PROP]).trim();
        if (a) {
          return a;
        }
      }
    } catch (e0) {}
    try {
      if (window[USERNAME_MEM_PROP]) {
        var b = String(window[USERNAME_MEM_PROP]).trim();
        if (b) {
          return b;
        }
      }
    } catch (e1) {}
    return "";
  }

  function writeUsernameToMemory(v) {
    try {
      if (window.top) {
        window.top[USERNAME_MEM_PROP] = v;
      }
    } catch (e0) {}
    try {
      window[USERNAME_MEM_PROP] = v;
    } catch (e1) {}
  }

  /** First-party cookie: survives reload on same host when iframe storage is cleared each load. */
  function readUsernameFromCookie() {
    try {
      var parts = String(document.cookie || "").split(";");
      var prefix = BUG_PLUGIN_USERNAME_KEY + "=";
      for (var i = 0; i < parts.length; i++) {
        var p = parts[i].trim();
        if (p.indexOf(prefix) === 0) {
          var raw = decodeURIComponent(p.substring(prefix.length));
          if (raw != null && String(raw).trim()) {
            return String(raw).trim();
          }
        }
      }
    } catch (eC) {}
    return "";
  }

  function writeUsernameToCookie(v) {
    try {
      var maxAge = 400 * 24 * 3600;
      var sec = "";
      try {
        if (String(location.protocol || "") === "https:") {
          sec = "; Secure";
        }
      } catch (e0) {}
      document.cookie =
        BUG_PLUGIN_USERNAME_KEY +
        "=" +
        encodeURIComponent(v) +
        "; path=/; max-age=" +
        maxAge +
        "; SameSite=Lax" +
        sec;
    } catch (e1) {}
  }

  function readLocalStorageUsername() {
    var roots = storageRoots();
    for (var i = 0; i < roots.length; i++) {
      try {
        var v = roots[i].localStorage.getItem(BUG_PLUGIN_USERNAME_KEY);
        if (v != null && String(v).trim()) {
          return String(v).trim();
        }
      } catch (e1) {}
    }
    return "";
  }

  function writeLocalStorageUsername(v) {
    var roots = storageRoots();
    for (var i = 0; i < roots.length; i++) {
      try {
        roots[i].localStorage.setItem(BUG_PLUGIN_USERNAME_KEY, v);
      } catch (e1) {}
    }
  }

  /** Same tab: memory → cookie → localStorage (iframe + top). */
  function readUsername() {
    var m = readUsernameFromMemory();
    if (m) {
      return m;
    }
    var ck = readUsernameFromCookie();
    if (ck) {
      return ck;
    }
    return readLocalStorageUsername();
  }

  function writeUsername(name) {
    var v = name != null ? String(name).trim() : "";
    if (!v) {
      return;
    }
    writeUsernameToMemory(v);
    writeUsernameToCookie(v);
    writeLocalStorageUsername(v);
  }

  /** ``UsernameManager`` uses the same read/write paths (iframe vs top). */
  function patchUsernameManagerStorage() {
    if (typeof UsernameManager === "undefined") {
      return;
    }
    var proto = UsernameManager.prototype;
    if (proto.__sonicMgmtPatchedStorage) {
      return;
    }
    proto.__sonicMgmtPatchedStorage = true;
    var origGet = proto.getStoredUsername;
    var origSave = proto.saveUsername;
    proto.getStoredUsername = function () {
      var cross = readUsername();
      if (cross) {
        return cross;
      }
      try {
        return origGet.call(this);
      } catch (eG) {
        return "";
      }
    };
    proto.saveUsername = function (username) {
      var ret = origSave.call(this, username);
      writeUsername(username);
      return ret;
    };
  }

  patchUsernameManagerStorage();

  function ensureUsernameForEmbed() {
    var cached = readUsername();
    if (cached) {
      return Promise.resolve(cached);
    }
    var um = new UsernameManager();
    return um.ensureUsername().then(function (name) {
      if (name) {
        writeUsername(name);
      }
      return name;
    });
  }

  function effectiveBugPostUrl() {
    try {
      var u = window.__sonicMgmtBugReportPostUrl;
      if (u != null && String(u).trim()) {
        u = String(u).trim();
        return u.endsWith("/") ? u : u + "/";
      }
    } catch (e0) {}
    return null;
  }

  function makeBugReportSender() {
    var s = new BugReportSender();
    var u = effectiveBugPostUrl();
    if (u) {
      s.serverUrl = u;
    }
    return s;
  }

  /** Allure report UI lives in ``window.top``; Failure analysis HTML runs in an iframe. */
  function getAllureReportWindow() {
    try {
      if (window.top && window.top.location) {
        void window.top.location.href;
        return window.top;
      }
    } catch (e0) {}
    return window;
  }

  /**
   * Same data as ``BugDataCollector.collectBugData`` / extension, without editing AllurClick2RM:
   * uses ``new BugDataCollector(null).fetchTestData`` / ``fetchEnvironmentData`` / ``findSysdumpPathFromTestStage``.
   * Keep the ``overviewData`` switch in sync with ``BugDataCollector.js`` ``collectBugData``.
   * ``allureWindow`` must be the report tab (e.g. ``window.top``) when this script runs in an iframe.
   */
  function fetchAllureBugContextForEmbed(allureWindow) {
    var w = allureWindow || window;
    if (!w || !w.location) {
      return Promise.resolve(null);
    }
    var hashMatch = w.location.hash.match(/#suites\/[^/]+\/([^/]+)/);
    if (!hashMatch) {
      return Promise.resolve(null);
    }
    if (typeof BugDataCollector === "undefined") {
      return Promise.resolve(null);
    }
    var testCaseId = hashMatch[1];
    var baseUrl = w.location.href.split("/index.html")[0];
    var is_session_report = baseUrl.indexOf("session-reports") >= 0;
    var collector = new BugDataCollector(null);
    return collector.fetchTestData(baseUrl, testCaseId).then(function (testData) {
      return collector.fetchEnvironmentData(baseUrl).then(function (env) {
        var overviewData = env.overviewData;
        var setupName = env.setupName;
        var sysdumpPath = collector.findSysdumpPathFromTestStage(testData.testStage);
        var initialBugData = {
          description:
            (testData.testStage && testData.testStage.description) || "",
          report_url: w.location.href,
          setup_name: setupName || "???",
          dump_files:
            sysdumpPath && sysdumpPath !== "Not found"
              ? [sysdumpPath]
              : ["not available"],
          pytest_cmd_args: "???",
          hw_sku: "???",
          beforeStages: testData.beforeStages || []
        };
        if (overviewData && overviewData.length > 0) {
          overviewData.forEach(function (item) {
            if (item.name && item.values && item.values.length > 0) {
              var val = item.values[0];
              switch (item.name) {
                case "PyTest_args":
                  if (!is_session_report) {
                    if (testData.fullName.indexOf("#") >= 0) {
                      var testNamePart = testData.fullName.split("#")[1];
                      initialBugData.pytest_cmd_args =
                        val + ' -k="' + testNamePart + '"';
                    } else {
                      initialBugData.pytest_cmd_args = val;
                    }
                  } else {
                    initialBugData.pytest_cmd_args = "???";
                  }
                  break;
                case "HwSKU":
                  initialBugData.hw_sku = val;
                  break;
                case "Version":
                  if (val && String(val).trim() !== "") {
                    initialBugData.detected_in_version = val;
                  }
                  break;
              }
            }
          });
        }
        var hasVersion =
          overviewData &&
          overviewData.some(function (item) {
            return (
              item.name === "Version" &&
              item.values &&
              item.values.length > 0 &&
              item.values[0] &&
              String(item.values[0]).trim() !== ""
            );
          });
        return {
          testData: testData,
          initialBugData: initialBugData,
          hasVersion: !!hasVersion,
          setupName: setupName,
          sysdumpPath: sysdumpPath,
          overviewData: overviewData,
          is_session_report: is_session_report,
          reportHref: w.location.href
        };
      });
    });
  }

  /**
   * Same field names as ``BugDataCollector.prepareBugReportData`` / ``create_rm_bug.create_data_for_rm_api``.
   */
  function mergeFailureAnalysisFlatPayload(opts, selectionResult, bugAuthor) {
    var bugData = (opts && opts.bugData) || {};
    var testName = (opts && opts.testName) || "Unknown Test";
    var nodeid = (opts && opts.testNodeid) || "";
    var fullName = nodeid ? testName + " [" + nodeid + "]" : testName;
    var reportUrl = bugData.report_url || "";
    if (!reportUrl) {
      try {
        reportUrl = String(window.top.location.href || "");
      } catch (e0) {
        reportUrl = String(window.location.href || "");
      }
    }
    var setupNm = bugData.setup_name || (opts && opts.setupName) || "???";
    return {
      test_name: fullName,
      description: selectionResult.bugDescription || "",
      report_url: reportUrl,
      is_test_function_failed: true,
      bug_title: selectionResult.bugTitle,
      project: selectionResult.team,
      branch: "not mentioned",
      user: "log_analyzer",
      show_stopper: selectionResult.showStopper,
      is_degradation: selectionResult.isDegradation,
      bug_author: bugAuthor,
      detected_in_version:
        selectionResult.manualVersion || bugData.detected_in_version || "",
      setup_name: setupNm,
      pytest_cmd_args: bugData.pytest_cmd_args || "???",
      hw_sku: bugData.hw_sku || "???",
      dump_files: bugData.dump_files && bugData.dump_files.length ? bugData.dump_files : []
    };
  }

  function openFromAllureAttachment(opts) {
    var fallbackBug = (opts && opts.bugData) || {};

    function resolveEmbedDraftKey() {
      if (opts && opts.testNodeid && String(opts.testNodeid).trim()) {
        return String(opts.testNodeid).trim();
      }
      return BugDraftStorage.resolveDraftKey(null, fallbackBug);
    }

    function showModal(bugAuthor, testName, setupName, hasVersion, bugData) {
      var ui = new BugReportUI();
      var modal = ui.createModal();
      modal.id = "fa-click2rm-modal-root";
      var embedDraftKey = resolveEmbedDraftKey();
      var content = ui.createBugInputForm(
        testName,
        setupName,
        hasVersion,
        bugData,
        embedDraftKey
      );
      modal.appendChild(content);
      document.body.appendChild(modal);

      function onResolve(selectionResult) {
        if (!selectionResult) {
          return;
        }
        var draftKey = ui.lastDraftKey || embedDraftKey;
        var flat = mergeFailureAnalysisFlatPayload(opts, selectionResult, bugAuthor);
        var sender = makeBugReportSender();
        Promise.resolve(sender.sendBugReport(flat))
          .then(function (result) {
            if (result && result.success) {
              ui.clearBugFormDraft(draftKey);
            } else {
              ui.saveBugFormDraftFromSelection(draftKey, selectionResult);
            }
          })
          .catch(function (err) {
            ui.saveBugFormDraftFromSelection(draftKey, selectionResult);
            try {
              alert(
                "Failed to create bug: " +
                  (err && err.message ? err.message : String(err))
              );
            } catch (eA) {}
            console.error(err);
          });
      }
      ui.setupModalEventHandlers(modal, content, onResolve, hasVersion);
    }

    ensureUsernameForEmbed()
      .then(function (bugAuthor) {
        if (!bugAuthor) {
          return;
        }
        if (typeof BugDataCollector !== "undefined") {
          return fetchAllureBugContextForEmbed(getAllureReportWindow())
            .then(function (ctx) {
              var testName =
                (opts && opts.testName) ||
                (ctx && ctx.testData && ctx.testData.name) ||
                "";
              if (ctx) {
                var merged = Object.assign({}, ctx.initialBugData, fallbackBug);
                if (fallbackBug.description) {
                  merged.description = fallbackBug.description;
                }
                if (fallbackBug.agentAnalysis !== undefined) {
                  merged.agentAnalysis = fallbackBug.agentAnalysis;
                }
                var setupNm =
                  (ctx.setupName && String(ctx.setupName).trim()) ||
                  ((opts && opts.setupName) || "").trim() ||
                  merged.setup_name ||
                  "???";
                showModal(bugAuthor, testName, setupNm, ctx.hasVersion, merged);
                return;
              }
              var setupLegacy = ((opts && opts.setupName) || "").trim() || "???";
              var hasLegacy =
                opts &&
                opts.hasVersion !== undefined &&
                opts.hasVersion !== null
                  ? !!opts.hasVersion
                  : false;
              try {
                alert(
                  "Could not load Allure test/environment data (need report URL with #suites/...). Using minimal bug fields."
                );
              } catch (eAl) {}
              showModal(bugAuthor, testName, setupLegacy, hasLegacy, fallbackBug);
            })
            .catch(function (fetchErr) {
              try {
                alert(
                  "Allure bug context fetch failed: " +
                    (fetchErr && fetchErr.message
                      ? fetchErr.message
                      : String(fetchErr))
                );
              } catch (eF) {}
              console.error(fetchErr);
              var setupLegacy = ((opts && opts.setupName) || "").trim() || "???";
              var hasLegacy =
                opts &&
                opts.hasVersion !== undefined &&
                opts.hasVersion !== null
                  ? !!opts.hasVersion
                  : false;
              var testName = (opts && opts.testName) || "";
              showModal(bugAuthor, testName, setupLegacy, hasLegacy, fallbackBug);
            });
        }
        var testName = (opts && opts.testName) || "";
        var setupName = ((opts && opts.setupName) || "").trim() || "???";
        var hasVersion =
          opts &&
          opts.hasVersion !== undefined &&
          opts.hasVersion !== null
            ? !!opts.hasVersion
            : false;
        showModal(bugAuthor, testName, setupName, hasVersion, fallbackBug);
      })
      .catch(function (err) {
        try {
          alert(
            "Bug reporter init failed: " +
              (err && err.message ? err.message : String(err))
          );
        } catch (eB) {}
        console.error(err);
      });
  }

  function closeModalIfOpen() {
    var el = document.getElementById("fa-click2rm-modal-root");
    if (el) el.remove();
  }

  window.__sonicMgmtFailureAnalysisRmModal = {
    openFromAllureAttachment: openFromAllureAttachment,
    closeModalIfOpen: closeModalIfOpen
  };
})();
