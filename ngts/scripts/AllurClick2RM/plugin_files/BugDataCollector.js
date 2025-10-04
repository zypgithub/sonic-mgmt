class BugDataCollector {
    constructor() {
        this.bugAuthor = "otrabelsi";
    }

    findSysdumpPathFromTestStage(reportContent) {
        if (!reportContent) return "Not found";
        function searchSteps(steps) {
            if (!steps || !Array.isArray(steps)) return "Not found";
            for (const step of steps) {
                if (step.name) {
                    if (step.name.startsWith("Completed sysdump:")) {
                        return step.name.replace("Completed sysdump:", "").trim();
                    }
                    if (step.name.startsWith("Copy dump ") && step.name.includes(" to log folder ")) {
                        const match = step.name.match(/Copy dump .+? to log folder (.+)/);
                        if (match) {
                            return match[1].trim();
                        }
                    }
                }
                const subStepResult = searchSteps(step.steps);
                if (subStepResult !== "Not found") return subStepResult;
            }
            return "Not found";
        }
        return searchSteps(reportContent.steps);
    }

    async fetchTestData(baseUrl, testCaseId) {
        const testUrl = `${baseUrl}/data/test-cases/${testCaseId}.json`;
        const testResp = await fetch(testUrl, { credentials: "include" });
        if (!testResp.ok) throw new Error(`Failed to fetch test JSON: ${testResp.status}`);
        return await testResp.json();
    }

    async fetchEnvironmentData(baseUrl) {
        let setupName = "";
        let overviewData = null;
        const overviewUrl = `${baseUrl}/widgets/environment.json`;
        const overviewResp = await fetch(overviewUrl, { credentials: "include" });
        if (overviewResp.ok) {
            overviewData = await overviewResp.json();
            const dutHostItem = overviewData.find(item => item.name === "Dut_host");
            if (dutHostItem && dutHostItem.values && dutHostItem.values.length > 0) {
                setupName = dutHostItem.values[0];
            }
        }
        return { overviewData, setupName };
    }

    prepareBugReportData(testData, selectionResult, sysdumpPath, overviewData, is_session_report) {
        const { team: selectedTeam, showStopper: showStopperValue, isDegradation: isDegradationValue, bugTitle: userBugTitle, manualVersion } = selectionResult;
        // Base flatData
        const flatData = {
            test_name: testData.fullName || "Not found",
            // test_description: (testData.testStage && testData.testStage.description) || "Not found",
            description: (testData.testStage && testData.testStage.description) || "",
            report_url: window.location.href,
            is_test_function_failed: true,
            bug_title: userBugTitle ,
            project: selectedTeam,
            branch: "not mentioned",
            user: "log_analyzer",
            show_stopper: showStopperValue,
            is_degradation: isDegradationValue,
            bug_author: this.bugAuthor
        };
        if (sysdumpPath && sysdumpPath !== "Not found") {
            flatData.dump_files = [sysdumpPath];
        }
        if (overviewData && overviewData.length > 0) {
            overviewData.forEach(item => {
                if (item.name && item.values && item.values.length > 0) {
                    const val = item.values[0];
                    switch (item.name) {
                        case "PyTest_args":
                            if (!is_session_report) {
                                if (flatData.test_name.includes('#')) {
                                    const testNamePart = flatData.test_name.split('#')[1];
                                    flatData.pytest_cmd_args = val + ` -k="${testNamePart}"`;
                                } else {
                                    flatData.pytest_cmd_args = val;
                                }
                            } else {
                                flatData.pytest_cmd_args = "???";
                            }
                            break;
                        case "HwSKU":
                            flatData.hw_sku = val;
                            break;
                        case "ASIC":
                            flatData.system_type = val;
                            break;
                        case "Version":
                            flatData.detected_in_version = val;
                            break;
                        case "Dut_host":
                            flatData.setup_name = val;
                            break;
                        case "Mars_Session":
                            flatData.mars_session = val;
                            break;
                        default:
                            // ignore other keys
                            break;
                    }
                }
            });
        }
        // If manual version was provided and detected_in_version is not set, use manual version
        if (manualVersion && !flatData.detected_in_version) {
            flatData.detected_in_version = manualVersion;
        }
        return flatData;
    }

    async collectBugData(ui) {
        try {
            // Get test data first to show test name in popup
            const hashMatch = window.location.hash.match(/#suites\/[^/]+\/([^/]+)/);
            if (!hashMatch) {
                alert("Cannot determine test case ID from URL");
                return;
            }
            const testCaseId = hashMatch[1];
            const baseUrl = window.location.href.split("/index.html")[0];
            const is_session_report = baseUrl.includes("session-reports");
            const testData = await this.fetchTestData(baseUrl, testCaseId);
            const { overviewData, setupName } = await this.fetchEnvironmentData(baseUrl);
            // Show popup
            const hasOverviewData = overviewData && overviewData.length > 0;
            const selectionResult = await ui.getUserBugInputs(testData.name, setupName, hasOverviewData);
            if (!selectionResult) {
                console.log("User cancelled bug creation");
                return;
            }
            const sysdumpPath = this.findSysdumpPathFromTestStage(testData.testStage);
            const flatData = this.prepareBugReportData(testData, selectionResult, sysdumpPath, overviewData, is_session_report);
            return flatData;
        } catch (err) {
            console.error("❌ Failed to extract data:", err);
            throw err;
        }
    }
}
