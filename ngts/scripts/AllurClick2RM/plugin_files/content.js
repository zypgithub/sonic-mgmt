// Main orchestration file for Bug Report Extension
(function () {
    const ui = new BugReportUI();
    const dataCollector = new BugDataCollector();
    const sender = new BugReportSender();
    async function handleBugReport() {
        try {
            const bugData = await dataCollector.collectBugData(ui);
            await sender.sendBugReport(bugData);
        } catch (err) {
            console.error("❌ Bug reporting failed:", err);
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
