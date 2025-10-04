class BugReportSender {
    constructor() {
        this.serverUrl = "https://rm-via-allure.nvidia.com:8443/";
    }
    async sendBugReport(bugData) {
        try {
            const resp = await fetch(this.serverUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(bugData)
            });
            if (!resp.ok) throw new Error(`Server error: ${resp.status}`);
            const result = await resp.json();
            console.log("✅ Server response:", result);
            return this.handleServerResponse(result);
        } catch (err) {
            console.error("❌ Failed to send data:", err);
            throw err;
        }
    }
    handleServerResponse(result) {
        const outputText = result.output || "No output received from server";
        // Check for failure
        if (outputText.includes("failed to create bug")) {
            alert(`❌ Failed to create bug!`);
            console.error("Server response:", outputText);
            return { success: false, message: "Bug creation failed" };
        }

        // Look for Redmine URL in the response
        const redmineMatch = outputText.match(/https:\/\/redmine\.[^\s'",]+/);
        if (redmineMatch) {
            const bugUrl = redmineMatch[0];
            if (confirm(`✅ Bug created successfully!\n\n🔗 URL: ${bugUrl}\n\nClick OK to open the bug in Redmine, or Cancel to stay here.`)) {
                window.open(bugUrl, '_blank');
            }
            return { success: true, url: bugUrl };
        }
        alert(`No bug was created`);
        return { success: false, message: "No bug URL found in response" };
    }
}
