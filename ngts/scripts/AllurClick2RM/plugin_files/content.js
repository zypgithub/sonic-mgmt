// Main orchestration file for Bug Report Extension
(function () {
    const usernameManager = new UsernameManager();
    const ui = new BugReportUI();
    const dataCollector = new BugDataCollector(usernameManager);
    const sender = new BugReportSender();
    async function handleBugReport() {
        try {
            const bugData = await dataCollector.collectBugData(ui);
            if (!bugData) {
                console.log("Bug creation cancelled by user");
                return;
            }
            const draftKey = ui.lastDraftKey;
            const result = await sender.sendBugReport(bugData);
            if (result && result.success) {
                ui.clearBugFormDraft(draftKey);
            } else {
                ui.saveBugFormDraftFromSelection(draftKey, ui.lastSelectionResult);
            }
        } catch (err) {
            console.error("❌ Bug reporting failed:", err);
            ui.saveBugFormDraftFromSelection(ui.lastDraftKey, ui.lastSelectionResult);
            alert("Failed to create bug report. See console for details.");
        }
    }
    function addButton() {
        ui.addButton(handleBugReport);
    }
    function removeButton() {
        ui.removeButton();
    }
    function checkPage() {
        if (/^#suites\/[^/]+\/[^/]+\/?$/.test(window.location.hash)) {
            addButton();
        } else {
            removeButton();
        }
    }
    // Initialize the extension
    checkPage();
    window.addEventListener("hashchange", checkPage);
    const observer = new MutationObserver(checkPage);
    observer.observe(document.body, { childList: true, subtree: true });
})();
