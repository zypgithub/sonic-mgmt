class BugReportUI {
    constructor() {
        this.buttonAdded = false;
    }

    createModal() {
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.5); z-index: 10000; display: flex;
            align-items: center; justify-content: center;
            pointer-events: none;   /* ✅ allow mouse scroll to pass through */
        `;
        return modal;
    }

    createBugInputForm(testName, setupName, hasOverviewData) {
        const content = document.createElement('div');
        content.style.cssText = `
            background: white; padding: 20px; border-radius: 8px;
            width: 600px; max-width: 90vw; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            pointer-events: auto;   /* ✅ re-enable events for popup */
        `;
        const versionFieldHtml = !hasOverviewData ? `
            <div style="margin: 15px 0; border-top: 1px solid #eee; padding-top: 15px;">
                <label style="display: block; margin-bottom: 8px; font-weight: bold; color: #d32f2f;">
                    Version: <span style="color: #d32f2f;">*</span>
                </label>
                <input type="text" id="versionInput"
                    placeholder="No version in Allure, please fill manually"
                    style="width: 100%; padding: 8px; border: 1px solid #d32f2f; border-radius: 4px; box-sizing: border-box;">
                <small style="color: #d32f2f; display: block; margin-top: 4px;">* This field is mandatory</small>
            </div>
        ` : '';
        content.innerHTML = `
            <h3 style="margin-top: 0; color: #333; border-bottom: 1px solid #eee; padding-bottom: 10px; font-weight: normal;">
                <strong>Open Bug for: </strong> ${testName || 'Unknown Test'}${setupName ? ' | ' + setupName : ''}
            </h3>
            <h4 style="margin: 15px 0 10px 0; color: #666;">Please select bug team:</h4>
            <div style="margin: 15px 0;">
                <label style="display: block; margin-bottom: 10px; cursor: pointer;">
                    <input type="radio" name="bugTeam" value="sonic-verification" checked style="margin-right: 8px;">
                    SONiC-Verification
                </label>
                <label style="display: block; margin-bottom: 10px; cursor: pointer;">
                    <input type="radio" name="bugTeam" value="sonic-design" style="margin-right: 8px;">
                    SONiC-Design
                </label>
            </div>
            <div style="margin: 15px 0; border-top: 1px solid #eee; padding-top: 15px;">
                <label style="display: block; margin-bottom: 8px; font-weight: bold;">
                    Bug Title:
                </label>
                <input type="text" id="bugTitleInput"
                    value="[Functional / Non-Functional ] [optional: &quot;Keyword&quot;] | user symptoms"
                    style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;">
            </div>
            ${versionFieldHtml}
            <div style="margin: 15px 0; border-top: 1px solid #eee; padding-top: 15px;">
                <label style="display: block; cursor: pointer;">
                    <input type="checkbox" id="showStopperCheck" value="1" style="margin-right: 8px;">
                    Show Stopper
                </label>
            </div>
            <div style="margin: 15px 0; border-top: 1px solid #eee; padding-top: 15px;">
                <label style="display: block; cursor: pointer;">
                    <input type="checkbox" id="isDegradationCheck" value="Degradation" style="margin-right: 8px;">
                    Is_Degradation
                </label>
            </div>
            <div style="text-align: right; margin-top: 20px;">
                <button id="cancelBtn" style="margin-right: 10px; padding: 8px 16px; background: #ccc; color: black; border: none; border-radius: 4px; cursor: pointer;">
                    Cancel
                </button>
                <button id="okBtn" style="padding: 8px 16px; background: #007cba; color: white; border: none; border-radius: 4px; cursor: pointer;">
                    OK
                </button>
            </div>
        `;
        return content;
    }

    setupModalEventHandlers(modal, content, resolve, hasOverviewData) {
        // ✅prevent keys from affecting Allure page while typing
        // Only stop propagation to parent page, but allow normal input behavior
        content.querySelectorAll('input, textarea').forEach(el => {
            el.addEventListener('keydown', (e) => {
                e.stopPropagation();
            });
        });
        // Handle OK button
        content.querySelector('#okBtn').addEventListener('click', () => {
            // Validate version field if overview data is not available
            if (!hasOverviewData) {
                const versionInput = content.querySelector('#versionInput');
                const versionValue = versionInput ? versionInput.value.trim() : "";
                if (!versionValue) {
                    alert('Version field is mandatory. Please fill in the version.');
                    versionInput.focus();
                    return;
                }
            }
            const selectedRadio = content.querySelector('input[name="bugTeam"]:checked');
            const selectedTeam = selectedRadio ? selectedRadio.value : null;
            const showStopperCheck = content.querySelector('#showStopperCheck');
            const showStopperValue = showStopperCheck && showStopperCheck.checked ? "1" : "0";
            const isDegradationCheck = content.querySelector('#isDegradationCheck');
            const isDegradationValue = isDegradationCheck && isDegradationCheck.checked ? "Degradation" : "";
            const bugTitleInput = content.querySelector('#bugTitleInput');
            const bugTitleValue = bugTitleInput ? bugTitleInput.value.trim() : "";
            const versionInput = content.querySelector('#versionInput');
            const manualVersion = versionInput ? versionInput.value.trim() : null;
            modal.remove();
            resolve({ team: selectedTeam, showStopper: showStopperValue, isDegradation: isDegradationValue, bugTitle: bugTitleValue, manualVersion: manualVersion });
        });
        // Handle Cancel button
        content.querySelector('#cancelBtn').addEventListener('click', () => {
            modal.remove();
            resolve(null); // Return null when cancelled
        });
        // Close on background click (also cancels)
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
                resolve(null); // Return null when cancelled
            }
        });
    }

    getUserBugInputs(testName, setupName, hasOverviewData) {
        return new Promise((resolve) => {
            const modal = this.createModal();
            const content = this.createBugInputForm(testName, setupName, hasOverviewData);
            modal.appendChild(content);
            document.body.appendChild(modal);
            this.setupModalEventHandlers(modal, content, resolve, hasOverviewData);
        });
    }

    addButton(onClickCallback) {
        if (this.buttonAdded) return;

        const button = document.createElement("button");
        button.id = "extractDataBtn";
        button.innerText = "🐞";
        button.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center;">
            <span style="font-size: 14px;">🐞</span>
            <span style="font-size: 7px; margin-top: 0.5px;">RM</span>
        </div>
        `;
        Object.assign(button.style, {
            position: "fixed",
            bottom: "20px",
            right: "20px",
            width: "30px",
            height: "30px",
            backgroundColor: "white",
            color: "black",
            border: "2px solid black",
            borderRadius: "50%",
            cursor: "pointer",
            zIndex: 9999,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: "bold"
        });
        document.body.appendChild(button);
        this.buttonAdded = true;

        button.addEventListener("click", onClickCallback);
    }

    removeButton() {
        const btn = document.getElementById("extractDataBtn");
        if (btn) {
            btn.remove();
            this.buttonAdded = false;
        }
    }
}
