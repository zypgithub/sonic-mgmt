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
        // Look for Redmine URL in the response FIRST (success case)
        const redmineMatch = outputText.match(/https:\/\/redmine\.[^\s'",]+/);
        if (redmineMatch) {
            const bugUrl = redmineMatch[0];
            this.showCustomConfirm(bugUrl);
            return { success: true, url: bugUrl };
        }
        //Check for specific error status (e.g., rate limiting)
        if (result.status === "error" && result.message) {
            this.showCustomAlert(`${result.message}`, 'error');
            console.error("Server error:", result.message);
            return { success: false, message: result.message };
        }
        // THIRD: Check for other specific failures in output
        if (outputText.includes("failed to create bug")) {
            this.showCustomAlert(`❌ Failed to create bug!`, 'error');
            console.error("Server response:", outputText);
            return { success: false, message: "Bug creation failed" };
        }
        // FINALLY: Generic fallback message
        this.showCustomAlert(`❌ Bug was not created`, 'warning');
        return { success: false, message: "No bug URL found in response" };
    }
    showCustomAlert(message, type = 'info') {
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.5); z-index: 10000;
            display: flex; align-items: center; justify-content: center;
        `;
        const box = document.createElement('div');
        box.style.cssText = `
            background: white; padding: 30px; border-radius: 10px;
            max-width: 500px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            text-align: center; font-family: Arial, sans-serif;
        `;
        const icon = type === 'error' ? '❌' : type === 'warning' ? '⚠️' : 'ℹ️';
        box.innerHTML = `
            <div style="font-size: 48px; margin-bottom: 20px;">${icon}</div>
            <div style="font-size: 16px; margin-bottom: 25px; color: #333;">${message}</div>
            <button id="alertOkBtn" style="
                background: #4CAF50; color: white; border: none;
                padding: 12px 30px; border-radius: 5px; cursor: pointer;
                font-size: 16px; font-weight: bold;
            ">OK</button>
        `;
        modal.appendChild(box);
        document.body.appendChild(modal);
        document.getElementById('alertOkBtn').addEventListener('click', () => {
            document.body.removeChild(modal);
        });
        // Close on background click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                document.body.removeChild(modal);
            }
        });
    }
    showCustomConfirm(bugUrl) {
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.5); z-index: 10000;
            display: flex; align-items: center; justify-content: center;
        `;
        const box = document.createElement('div');
        box.style.cssText = `
            background: white; padding: 30px; border-radius: 10px;
            max-width: 600px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            text-align: center; font-family: Arial, sans-serif;
        `;
        box.innerHTML = `
            <div style="font-size: 48px; margin-bottom: 20px;">✅</div>
            <div style="font-size: 18px; font-weight: bold; margin-bottom: 15px; color: #2e7d32;">
                Bug created successfully!
            </div>
            <div style="margin-bottom: 20px; word-break: break-all;">
                <div style="font-size: 14px; color: #666; margin-bottom: 8px;">🔗 URL:</div>
                <a href="${bugUrl}" target="_blank" style="color: #1976d2; text-decoration: none; font-size: 14px;">
                    ${bugUrl}
                </a>
            </div>
            <div style="display: flex; gap: 10px; justify-content: center;">
                <button id="confirmOpenBtn" style="
                    background: #4CAF50; color: white; border: none;
                    padding: 12px 30px; border-radius: 5px; cursor: pointer;
                    font-size: 16px; font-weight: bold;
                ">Open in Redmine</button>
                <button id="confirmCancelBtn" style="
                    background: #757575; color: white; border: none;
                    padding: 12px 30px; border-radius: 5px; cursor: pointer;
                    font-size: 16px; font-weight: bold;
                ">Stay Here</button>
            </div>
        `;
        modal.appendChild(box);
        document.body.appendChild(modal);
        document.getElementById('confirmOpenBtn').addEventListener('click', () => {
            window.open(bugUrl, '_blank');
            document.body.removeChild(modal);
        });
        document.getElementById('confirmCancelBtn').addEventListener('click', () => {
            document.body.removeChild(modal);
        });
        // Close on background click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                document.body.removeChild(modal);
            }
        });
    }
}
