/**
 * Persists in-progress bug form edits per test (localStorage).
 * Restored when the user reopens the modal after Cancel or a failed create.
 */
class BugDraftStorage {
    static STORAGE_PREFIX = "allurClick2Rm_draft_v1_";

    static resolveDraftKey(explicitKey, bugData) {
        if (explicitKey != null && String(explicitKey).trim() !== "") {
            return String(explicitKey).trim();
        }
        try {
            const hashMatch = window.location.hash.match(/#suites\/[^/]+\/([^/]+)/);
            if (hashMatch) {
                return hashMatch[1];
            }
        } catch (eHash) {}
        if (bugData && bugData.report_url) {
            try {
                const m = String(bugData.report_url).match(/#suites\/[^/]+\/([^/]+)/);
                if (m) {
                    return m[1];
                }
            } catch (eUrl) {}
        }
        return null;
    }

    static load(draftKey) {
        if (!draftKey) {
            return null;
        }
        try {
            const raw = localStorage.getItem(this.STORAGE_PREFIX + draftKey);
            if (!raw) {
                return null;
            }
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== "object") {
                return null;
            }
            return parsed;
        } catch (e) {
            console.warn("BugDraftStorage.load failed:", e);
            return null;
        }
    }

    static save(draftKey, formState) {
        if (!draftKey || !formState) {
            return;
        }
        try {
            localStorage.setItem(
                this.STORAGE_PREFIX + draftKey,
                JSON.stringify({
                    team: formState.team,
                    showStopper: formState.showStopper,
                    isDegradation: formState.isDegradation,
                    bugTitle: formState.bugTitle,
                    bugDescription: formState.bugDescription,
                    manualVersion: formState.manualVersion,
                    savedAt: Date.now()
                })
            );
        } catch (e) {
            console.warn("BugDraftStorage.save failed:", e);
        }
    }

    static clear(draftKey) {
        if (!draftKey) {
            return;
        }
        try {
            localStorage.removeItem(this.STORAGE_PREFIX + draftKey);
        } catch (e) {
            console.warn("BugDraftStorage.clear failed:", e);
        }
    }

    static fromSelectionResult(selectionResult) {
        if (!selectionResult) {
            return null;
        }
        return {
            team: selectionResult.team,
            showStopper: selectionResult.showStopper,
            isDegradation: selectionResult.isDegradation,
            bugTitle: selectionResult.bugTitle,
            bugDescription: selectionResult.bugDescription,
            manualVersion: selectionResult.manualVersion
        };
    }
}
