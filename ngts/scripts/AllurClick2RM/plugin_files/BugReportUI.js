class BugReportUI {
    constructor() {
        this.buttonAdded = false;
        this.HIGHLIGHT_COLOR = '#1abc9c';
        this.lastDraftKey = null;
        this.lastSelectionResult = null;
    }

    resolveDraftKey(explicitDraftKey, bugData) {
        return BugDraftStorage.resolveDraftKey(explicitDraftKey, bugData);
    }

    collectFormStateFromContent(content) {
        const versionInput = content.querySelector('#versionInput');
        const bugTitleInput = content.querySelector('#bugTitleInput');
        const selectedRadio = content.querySelector('input[name="bugTeam"]:checked');
        const showStopperCheck = content.querySelector('#showStopperCheck');
        const isDegradationCheck = content.querySelector('#isDegradationCheck');
        const editorDiv = content.querySelector('#editor');
        return {
            team: selectedRadio ? selectedRadio.value : null,
            showStopper: showStopperCheck && showStopperCheck.checked ? "1" : "0",
            isDegradation: isDegradationCheck && isDegradationCheck.checked ? "Degradation" : "",
            bugTitle: bugTitleInput ? bugTitleInput.value.trim() : "",
            bugDescription: editorDiv ? editorDiv.innerHTML : "",
            manualVersion: versionInput ? versionInput.value.trim() : ""
        };
    }

    applyDraftToContent(content, draft) {
        if (!draft) {
            return;
        }
        if (draft.team) {
            const teamRadio = content.querySelector(`input[name="bugTeam"][value="${draft.team}"]`);
            if (teamRadio) {
                teamRadio.checked = true;
            }
        }
        const bugTitleInput = content.querySelector('#bugTitleInput');
        if (bugTitleInput && draft.bugTitle != null && String(draft.bugTitle).length > 0) {
            bugTitleInput.value = draft.bugTitle;
        }
        const versionInput = content.querySelector('#versionInput');
        if (versionInput && draft.manualVersion) {
            versionInput.value = draft.manualVersion;
        }
        const editor = content.querySelector('#editor');
        if (editor && draft.bugDescription) {
            editor.innerHTML = draft.bugDescription;
        }
        const showStopperCheck = content.querySelector('#showStopperCheck');
        if (showStopperCheck) {
            showStopperCheck.checked = draft.showStopper === "1";
        }
        const isDegradationCheck = content.querySelector('#isDegradationCheck');
        if (isDegradationCheck) {
            isDegradationCheck.checked = draft.isDegradation === "Degradation";
        }
    }

    saveBugFormDraft(draftKey, content) {
        if (!draftKey) {
            return;
        }
        BugDraftStorage.save(draftKey, this.collectFormStateFromContent(content));
    }

    saveBugFormDraftFromSelection(draftKey, selectionResult) {
        if (!draftKey) {
            return;
        }
        const state = BugDraftStorage.fromSelectionResult(selectionResult);
        if (state) {
            BugDraftStorage.save(draftKey, state);
        }
    }

    clearBugFormDraft(draftKey) {
        BugDraftStorage.clear(draftKey);
    }

    async extractPytestCmdFromAttachment(bugData) {
        // Try to find pytest_run_test_cmd in beforeStages only
        const stages = bugData.beforeStages || [];
        for (const stage of stages) {
            if (stage.name && stage.name.startsWith('pytest_run_test_cmd')) {
                if (stage.attachments && stage.attachments.length > 0) {
                    const attachment = stage.attachments[0];
                    if (attachment.source) {
                        try {
                            // Construct the URL correctly - remove the hash and index.html
                            const currentUrl = window.location.href;
                            // Get base URL up to /index.html (or just the path before the hash)
                            const baseUrl = currentUrl.split('/index.html')[0];
                            const attachmentUrl = `${baseUrl}/data/attachments/${attachment.source}`;
                            console.log('Fetching pytest command from:', attachmentUrl);
                            // Add timeout to prevent hanging
                            const fetchPromise = fetch(attachmentUrl, {
                                credentials: 'include',
                                cache: 'no-cache'
                            }).then(async response => {
                                console.log('Fetch response:', response.status);
                                if (response.ok) {
                                    const content = await response.text();
                                    console.log('Successfully fetched pytest command');
                                    return content.trim();
                                } else {
                                    throw new Error(`HTTP ${response.status}`);
                                }
                            });
                            const timeoutPromise = new Promise((_, reject) =>
                                setTimeout(() => reject(new Error('Timeout')), 2000)
                            );
                            const result = await Promise.race([fetchPromise, timeoutPromise]);
                            return result;
                        } catch (error) {
                            console.warn('Failed to fetch pytest command:', error.message);
                            // Continue to fallback on any error
                        }
                    }
                }
            }
        }
        // Fallback to the original pytest_cmd_args
        return bugData.pytest_cmd_args || "???";
    }
    async createDescriptionTemplate(bugData) {
        try {
            const attachments = bugData.dump_files && bugData.dump_files.length > 0
                ? bugData.dump_files[0]
                : "not available";
            const reportUrl = bugData.report_url || "";
            const setupName = bugData.setup_name || "???";
            const pytestCmdArgs = await this.extractPytestCmdFromAttachment(bugData);
            const testDescription = bugData.description || "";
            const testbedTopology = this.extractTestbedTopology(pytestCmdArgs, setupName);
            const hwsku = bugData.hw_sku || "???";
            return `<p><ins><strong>Issue description</strong></ins></p>
                <p>${testDescription}</p>
                <br/>
                <ul>
                <li><strong>The test case is: <span style="color:${this.HIGHLIGHT_COLOR}">automated</span></strong></li>
                \t<li><strong>Duplicate Check:  <span style="color:${this.HIGHLIGHT_COLOR}">confirmed</span>/unconfirmed</strong></li>
                \t<li><strong>Is this a new test? <span style="color:${this.HIGHLIGHT_COLOR}">No</span></strong></li>
                \t<li><strong>How long it takes to reproduce the issue? <span style="color:${this.HIGHLIGHT_COLOR}">???</span></strong></li>
                \t<li><strong>How often the issue is reproduced and what probability? <span style="color:${this.HIGHLIGHT_COLOR}">???</span></strong></li>
                \t<li><strong>Is this a degradation(based on test result)? <span style="color:${this.HIGHLIGHT_COLOR}">???</span></strong></li>
                \t<li><strong>Is this a new flow or an existing flow that was changed recently: <span style="color:${this.HIGHLIGHT_COLOR}">Existing</span></strong></li>
                \t<li><strong>Root cause (if already detected): </strong></li>
                \t<li><strong>Test log(path/url):</strong> <a href="${reportUrl}"><strong>allure report</strong></a></li>
                </ul>
                <p><ins><strong>Setup description</strong></ins></p>
                <ul>
                \t<li><strong>Testbed name: <span style="color:${this.HIGHLIGHT_COLOR}">${setupName}</span></strong></li>
                \t<li><strong>Testbed topology: <span style="color:${this.HIGHLIGHT_COLOR}">topology: ${testbedTopology}, hwsku: ${hwsku}</span></strong></li>
                \t<li><strong>Which traffic runs on the setup:</strong></li>
                \t<li><strong>Topology diagram (optional):</strong></li>
                </ul>
                <p><ins><strong>Steps to reproduce</strong></ins></p>
                <ul>
                \t<li><strong>Run the test with the following command:</strong></li>
                </ul>
                <pre>${pytestCmdArgs}</pre>
                <ul>
                </ul>
                <p><ins><strong>Observed behavior</strong></ins></p>
                <p> <strong><span style="color:${this.HIGHLIGHT_COLOR}">????</span></strong></p>
                <p><strong><ins>Expected behavior</ins></strong></p>
                <p> <strong><span style="color:${this.HIGHLIGHT_COLOR}">????</span></strong></p>
                <p><ins><strong>Attachments</strong></ins></p>
                <p> <strong><span style="color:${this.HIGHLIGHT_COLOR}">Full dump is available in attachments:</span></strong></p>
                <pre>${attachments}</pre>`;
        } catch (error) {
            console.error('Error in createDescriptionTemplate:', error);
            // Return a basic template on error
            return `<p style="color: #d32f2f;">Error generating template. Please try again.</p>`;
        }
    }
    extractTestbedTopology(pytestCmdArgs, setupName) {
        // Try to extract topology from pytest command args
        if (pytestCmdArgs && pytestCmdArgs !== "???") {
            const topoMatch = pytestCmdArgs.match(/--testbed_name[=\s]+(\S+)/);
            if (topoMatch) {
                return topoMatch[1];
            }
        }
        // Fallback to setup name if available
        return setupName || "???";
    }
    createModal() {
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.5); z-index: 10000;
            pointer-events: none;   /* ✅ allow mouse scroll to pass through */
        `;
        return modal;
    }
    createBugInputForm(testName, setupName, hasVersion, bugData = null, draftKey = null) {
        const resolvedDraftKey = this.resolveDraftKey(draftKey, bugData);
        this.lastDraftKey = resolvedDraftKey;
        const savedDraft = resolvedDraftKey ? BugDraftStorage.load(resolvedDraftKey) : null;
        const content = document.createElement('div');
        content.style.cssText = `
            background: white; padding: 20px; border-radius: 10px;
            width: 45vw; min-width: 280px; max-width: 900px;
            max-height: 85vh;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            pointer-events: auto;   /* ✅ re-enable events for popup */
            position: absolute;
            left: 23%;
            top: 50%;
            transform: translate(-50%, -50%);
        `;
        content.dataset.bugFormDefaultLeft = '23%';
        content.dataset.bugFormDefaultTop = '50%';
        content.dataset.bugFormDefaultTransform = 'translate(-50%, -50%)';
        // Create close button (X)
        const closeButton = document.createElement('button');
        closeButton.id = 'closeBtn';
        closeButton.innerHTML = '×';
        closeButton.style.cssText = `
            position: absolute;
            top: -10px;
            right: -10px;
            background: white;
            border: 2px solid black;
            font-size: 20px;
            font-weight: bold;
            color: black;
            cursor: pointer;
            width: 30px;
            height: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0;
            line-height: 1;
            border-radius: 50%;
            transition: all 0.2s;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            z-index: 10003;
        `;
        closeButton.addEventListener('mouseenter', () => {
            closeButton.style.backgroundColor = '#d32f2f';
            closeButton.style.color = 'white';
            closeButton.style.borderColor = '#d32f2f';
            closeButton.style.transform = 'scale(1.15) rotate(90deg)';
        });
        closeButton.addEventListener('mouseleave', () => {
            closeButton.style.backgroundColor = 'white';
            closeButton.style.color = 'black';
            closeButton.style.borderColor = 'black';
            closeButton.style.transform = 'scale(1) rotate(0deg)';
        });
        // Create inner scrollable wrapper (id used by resize logic)
        const scrollWrapper = document.createElement('div');
        scrollWrapper.id = 'bugFormMainRow';
        scrollWrapper.style.cssText = `
            max-height: calc(85vh - 40px);
            overflow-y: auto;
            overflow-x: auto;
        `;
        // Create resize handle with padding
        const resizeHandle = document.createElement('div');
        resizeHandle.style.cssText = `
            position: absolute;
            bottom: -5px;
            right: -5px;
            width: 20px;
            height: 20px;
            cursor: nwse-resize;
            z-index: 10002;
            display: flex;
            align-items: center;
            justify-content: center;
            pointer-events: auto;
        `;
        resizeHandle.innerHTML = `
            <div style="
                width: 12px;
                height: 12px;
                background: repeating-linear-gradient(
                    -45deg,
                    transparent,
                    transparent 1px,
                    #888 1px,
                    #888 2px
                );
                border: 1px solid #ccc;
                border-radius: 2px;
                background-color: white;
                box-shadow: 0 1px 3px rgba(0,0,0,0.2);
            "></div>
        `;
        // Add resize functionality
        let isResizing = false;
        let startX, startY, startWidth, startHeight, startLeft, startTop;
        resizeHandle.addEventListener('mousedown', (e) => {
            isResizing = true;
            startX = e.clientX;
            startY = e.clientY;
            // Get computed values
            const rect = content.getBoundingClientRect();
            startWidth = rect.width;
            startHeight = rect.height;
            startLeft = rect.left;
            startTop = rect.top;
            e.preventDefault();
            e.stopPropagation();
        });
        const handleMouseMove = (e) => {
            if (!isResizing) return;
            const deltaX = e.clientX - startX;
            const deltaY = e.clientY - startY;
            // Calculate new dimensions
            const newWidth = Math.max(280, startWidth + deltaX);
            const newHeight = Math.max(400, startHeight + deltaY);
            // Update size without changing position
            content.style.width = newWidth + 'px';
            content.style.height = newHeight + 'px';
            content.style.maxWidth = 'none'; // Remove max-width constraint
            content.style.maxHeight = 'none';
            // Keep the scroll row in sync with explicit dialog height
            const mainRowEl = content.querySelector('#bugFormMainRow');
            if (mainRowEl) {
                mainRowEl.style.maxHeight = (newHeight - 40) + 'px';
            } else {
                scrollWrapper.style.maxHeight = (newHeight - 40) + 'px';
            }
            // Adjust position to keep top-left corner fixed
            const currentRect = content.getBoundingClientRect();
            const leftOffset = currentRect.left - startLeft;
            const topOffset = currentRect.top - startTop;
            if (leftOffset !== 0 || topOffset !== 0) {
                const currentLeft = parseFloat(content.style.left) || 23;
                content.style.left = (currentLeft - leftOffset) + 'px';
                const currentTopPercent = 50;
                content.style.top = (currentTopPercent - (topOffset / window.innerHeight * 100)) + '%';
            }
        };
        const handleMouseUp = () => {
            isResizing = false;
        };
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
        // Get version value from draft, then bugData
        const versionValue = (savedDraft && savedDraft.manualVersion)
            ? savedDraft.manualVersion
            : ((bugData && bugData.detected_in_version) ? bugData.detected_in_version : '');
        const versionPlaceholder = hasVersion ? "Version from Allure" : "Please fill in version";
        // Conditionally style based on whether there's a value
        const hasVersionValue = versionValue && versionValue.trim() !== '';
        const labelColor = hasVersionValue ? '#333' : '#d32f2f';
        const borderColor = hasVersionValue ? '#ccc' : '#d32f2f';
        const showMandatoryMessage = !hasVersionValue;
        // Always show version field (mandatory)
        const versionFieldHtml = `
            <div style="margin: 15px 0; border-top: 1px solid #eee; padding-top: 15px;">
                <label style="display: block; margin-bottom: 10px; font-weight: bold; color: ${labelColor};">
                    Version: ${showMandatoryMessage ? '<span style="color: #d32f2f;">*</span>' : ''}
                </label>
                <input type="text" id="versionInput"
                    value="${versionValue}"
                    placeholder="${versionPlaceholder}"
                    style="width: 100%; padding: 10px; border: 1px solid ${borderColor}; border-radius: 4px; box-sizing: border-box;">
                ${showMandatoryMessage ? '<small style="color: #d32f2f; display: block; margin-top: 4px;">* This field is mandatory</small>' : ''}
            </div>
        `;
        scrollWrapper.innerHTML = `
            <div style="margin: 0 0 8px 0; border-bottom: 1px solid #eee; padding-bottom: 10px;">
                <h3 style="margin: 0; width: 100%; color: #333; font-weight: normal; user-select: none;">
                    <strong>Open Bug for: </strong> ${testName || 'Unknown Test'}${setupName ? ' | ' + setupName : ''}
                </h3>
            </div>
            <h4 style="margin: 15px 0 10px 0; color: #666;">Please select bug team:</h4>
            <div style="margin: 15px 0; display: flex; gap: 20px;">
                <label style="display: inline-block; cursor: pointer; padding: 10px 10px; margin: -10px 0;">
                    <input type="radio" name="bugTeam" value="sonic-design" checked style="margin-right: 10px;">
                    SONiC-Design
                </label>
                <label style="display: inline-block; cursor: pointer; padding: 10px 10px; margin: -10px 0;">
                    <input type="radio" name="bugTeam" value="sonic-verification" style="margin-right: 10px;">
                    SONiC-Verification
                </label>
            </div>
            <div style="margin: 15px 0; border-top: 1px solid #eee; padding-top: 15px;">
                <label id="bugTitleLabel" style="display: block; margin-bottom: 10px; font-weight: bold; color: #d32f2f;">
                    Bug Title: <span style="color: #d32f2f;">*</span>
                </label>
                <input type="text" id="bugTitleInput"
                    value="[Functional / Non-Functional ] [optional: &quot;Keyword&quot;] | user symptoms"
                    style="width: 100%; padding: 10px; border: 1px solid #d32f2f; border-radius: 4px; box-sizing: border-box;">
                <small id="bugTitleWarning" style="color: #d32f2f; display: block; margin-top: 4px;">* Please change the placeholder text</small>
            </div>
            ${versionFieldHtml}
            <div style="margin: 15px 0; border-top: 1px solid #eee; padding-top: 15px;">
                <label style="display: block; margin-bottom: 10px; font-weight: bold;">
                    Bug Description:
                </label>
                <div style="border: 1px solid #ccc; border-radius: 4px; background: white;">
                    <div id="editorToolbar" style="display: flex; flex-wrap: wrap; gap: 2px; padding: 5px; background: #f5f5f5; border-bottom: 1px solid #ccc; border-radius: 4px 4px 0 0; position: relative;">
                        <button type="button" data-command="bold" title="Bold (Ctrl+B)" style="padding: 5px 10px; background: white; border: 1px solid #ccc; border-radius: 3px; cursor: pointer; font-weight: bold;">B</button>
                        <button type="button" data-command="italic" title="Italic (Ctrl+I)" style="padding: 5px 10px; background: white; border: 1px solid #ccc; border-radius: 3px; cursor: pointer; font-style: italic;">I</button>
                        <button type="button" data-command="underline" title="Underline (Ctrl+U)" style="padding: 5px 10px; background: white; border: 1px solid #ccc; border-radius: 3px; cursor: pointer; text-decoration: underline;">U</button>
                        <span style="width: 1px; background: #ccc; margin: 0 5px;"></span>
                        <div style="position: relative; display: inline-block;">
                            <button type="button" id="textColorBtn" title="Text Color" style="padding: 5px 10px; background: white; border: 1px solid #ccc; border-radius: 3px; cursor: pointer;">A▼</button>
                            <div id="textColorPalette" style="display: none; position: absolute; top: 100%; left: 0; margin-top: 2px; background: white; border: 1px solid #ccc; border-radius: 4px; padding: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); z-index: 1000; width: 180px;">
                                <div style="display: grid; grid-template-columns: repeat(6, 1fr); gap: 4px;"></div>
                            </div>
                        </div>
                        <div style="position: relative; display: inline-block;">
                            <button type="button" id="bgColorBtn" title="Background Color" style="padding: 5px 10px; background: white; border: 1px solid #ccc; border-radius: 3px; cursor: pointer;">🎨▼</button>
                            <div id="bgColorPalette" style="display: none; position: absolute; top: 100%; left: 0; margin-top: 2px; background: white; border: 1px solid #ccc; border-radius: 4px; padding: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); z-index: 1000; width: 180px;">
                                <div style="display: grid; grid-template-columns: repeat(6, 1fr); gap: 4px;"></div>
                            </div>
                        </div>
                        <span style="width: 1px; background: #ccc; margin: 0 5px;"></span>
                        <button type="button" data-command="insertUnorderedList" title="Bullet List" style="padding: 5px 10px; background: white; border: 1px solid #ccc; border-radius: 3px; cursor: pointer;">• List</button>
                        <button type="button" data-command="insertOrderedList" title="Numbered List" style="padding: 5px 10px; background: white; border: 1px solid #ccc; border-radius: 3px; cursor: pointer;">1. List</button>
                        <span style="width: 1px; background: #ccc; margin: 0 5px;"></span>
                        <button type="button" data-command="code" title="Code Block" style="padding: 5px 10px; background: white; border: 1px solid #ccc; border-radius: 3px; cursor: pointer; font-family: monospace;">&lt;/&gt;</button>
                        <button type="button" data-command="createLink" title="Insert Link" style="padding: 5px 10px; background: white; border: 1px solid #ccc; border-radius: 3px; cursor: pointer;">🔗 Link</button>
                    </div>
                    <style>
                        #editor pre {
                            background: #f4f4f4;
                            padding: 10px;
                            border-radius: 4px;
                            font-family: monospace;
                            color: #333;
                            white-space: pre-wrap;
                            display: block;
                            margin: 10px 0;
                            border: 1px solid #ddd;
                        }
                    </style>
                    <div id="editor" contenteditable="true" spellcheck="false"
                        style="min-height: 150px; max-height: 400px; overflow-y: auto; padding: 10px; outline: none;">
                    </div>
                </div>
            </div>
            <div style="margin: 15px 0; border-top: 1px solid #eee; padding-top: 15px;">
                <label style="display: inline-block; cursor: pointer; padding: 10px 10px; margin: -10px 0;">
                    <input type="checkbox" id="showStopperCheck" value="1" style="margin-right: 10px;">
                    Show Stopper
                </label>
            </div>
            <div style="margin: 15px 0; border-top: 1px solid #eee; padding-top: 15px;">
                <label style="display: inline-block; cursor: pointer; padding: 10px 10px; margin: -10px 0;">
                    <input type="checkbox" id="isDegradationCheck" value="Degradation" style="margin-right: 10px;">
                    Is_Degradation
                </label>
            </div>
            <div style="text-align: right; margin-top: 20px;">
                <button id="cancelBtn" style="margin-right: 10px; padding: 10px 16px; background: #ccc; color: black; border: none; border-radius: 4px; cursor: pointer;">
                    Cancel
                </button>
                <button id="okBtn" style="padding: 10px 16px; background: #007cba; color: white; border: none; border-radius: 4px; cursor: pointer;">
                    OK
                </button>
            </div>
        `;
        content.appendChild(closeButton);
        content.appendChild(scrollWrapper);
        content.appendChild(resizeHandle);
        if (savedDraft) {
            this.applyDraftToContent(scrollWrapper, savedDraft);
        } else if (bugData) {
            setTimeout(() => {
                const editor = scrollWrapper.querySelector('#editor');
                if (editor) {
                    editor.innerHTML = '<p style="color: #666; font-style: italic;">Loading template...</p>';
                }
            }, 0);
            this.createDescriptionTemplate(bugData).then(descriptionHtml => {
                setTimeout(() => {
                    const editor = scrollWrapper.querySelector('#editor');
                    if (editor) {
                        editor.innerHTML = descriptionHtml;
                    }
                }, 0);
            }).catch(error => {
                console.error('Error creating description template:', error);
                setTimeout(() => {
                    const editor = scrollWrapper.querySelector('#editor');
                    if (editor) {
                        editor.innerHTML = '<p style="color: #d32f2f;">Error loading template. Please try again.</p>';
                    }
                }, 0);
            });
        }
        content.dataset.draftKey = resolvedDraftKey || "";
        return content;
    }
    makeDraggable(element) {
        let isDragging = false;
        let currentX;
        let currentY;
        let initialX;
        let initialY;
        element.addEventListener('mousedown', (e) => {
            // Don't start dragging if clicking on interactive elements
            const target = e.target;
            if (target.tagName === 'INPUT' ||
                target.tagName === 'BUTTON' ||
                target.tagName === 'TEXTAREA' ||
                target.tagName === 'SELECT') {
                return;
            }
            // Don't drag when clicking on the editor or its toolbar
            if (target.id === 'editor' ||
                target.closest('#editor') ||
                target.closest('#editorToolbar') ||
                target.closest('#textColorPalette') ||
                target.closest('#bgColorPalette')) {
                return;
            }
            // For labels, only prevent dragging if they contain an input (radio/checkbox)
            if (target.tagName === 'LABEL') {
                const hasInput = target.querySelector('input');
                if (hasInput) {
                    return;
                }
            }
            isDragging = true;
            // Get the current position
            const rect = element.getBoundingClientRect();
            initialX = e.clientX - rect.left;
            initialY = e.clientY - rect.top;
            // Remove transform and set absolute positioning
            element.style.transform = 'none';
            element.style.left = rect.left + 'px';
            element.style.top = rect.top + 'px';
            element.style.cursor = 'move';
        });
        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            e.preventDefault();
            currentX = e.clientX - initialX;
            currentY = e.clientY - initialY;
            element.style.left = currentX + 'px';
            element.style.top = currentY + 'px';
        });
        document.addEventListener('mouseup', () => {
            if (isDragging) {
                isDragging = false;
                element.style.cursor = '';
            }
        });
    }
    setupModalEventHandlers(modal, content, resolve, hasVersion) {
        const draftKey = content.dataset.draftKey || this.lastDraftKey || null;
        const cancelModal = () => {
            this.saveBugFormDraft(draftKey, content);
            modal.remove();
            document.removeEventListener('keydown', handleEscKey, true);
            resolve(null);
        };
        // Initialize the rich text editor
        RichTextEditor.initialize(content);
        // Make the popup draggable from anywhere except interactive elements
        this.makeDraggable(content);
        // ✅prevent keys from affecting Allure page while typing
        // Only stop propagation to parent page, but allow ESC to close modal
        content.querySelectorAll('input, textarea, #editor').forEach(el => {
            el.addEventListener('keydown', (e) => {
                // Allow ESC to propagate so modal can be closed
                if (e.key !== 'Escape') {
                    e.stopPropagation();
                }
            });
        });
        // Add dynamic validation for version field
        const versionInput = content.querySelector('#versionInput');
        if (!versionInput) {
            console.error('BugReportUI: #versionInput not found in modal');
            return;
        }
        const versionLabel = versionInput.parentElement.querySelector('label');
        const updateVersionStyling = () => {
            const value = versionInput.value.trim();
            // Always query for the warning to get the latest one
            const versionWarning = versionInput.parentElement.querySelector('small');
            if (value === '') {
                // Empty - show red styling
                versionLabel.style.color = '#d32f2f';
                versionLabel.innerHTML = 'Version: <span style="color: #d32f2f;">*</span>';
                versionInput.style.borderColor = '#d32f2f';
                if (versionWarning) {
                    versionWarning.style.display = 'block';
                } else {
                    // Create warning if it doesn't exist
                    const warning = document.createElement('small');
                    warning.style.cssText = 'color: #d32f2f; display: block; margin-top: 4px;';
                    warning.textContent = '* This field is mandatory';
                    versionInput.parentElement.appendChild(warning);
                }
            } else {
                // Has value - normal styling
                versionLabel.style.color = '#333';
                versionLabel.innerHTML = 'Version:';
                versionInput.style.borderColor = '#ccc';
                if (versionWarning) {
                    versionWarning.style.display = 'none';
                }
            }
        };
        // Listen for input changes
        versionInput.addEventListener('input', updateVersionStyling);
        versionInput.addEventListener('blur', updateVersionStyling);
        // Add dynamic validation for bug title field
        const bugTitleInput = content.querySelector('#bugTitleInput');
        const bugTitleLabel = content.querySelector('#bugTitleLabel');
        const bugTitleWarning = content.querySelector('#bugTitleWarning');
        const bugTitlePlaceholder = "[Functional / Non-Functional ] [optional: \"Keyword\"] | user symptoms";
        const updateBugTitleStyling = () => {
            const value = bugTitleInput.value.trim();
            if (value === '' || value === bugTitlePlaceholder) {
                // Empty or still placeholder - show red styling
                bugTitleLabel.style.color = '#d32f2f';
                bugTitleLabel.innerHTML = 'Bug Title: <span style="color: #d32f2f;">*</span>';
                bugTitleInput.style.borderColor = '#d32f2f';
                if (bugTitleWarning) {
                    bugTitleWarning.style.display = 'block';
                }
            } else {
                // Has been changed - normal styling
                bugTitleLabel.style.color = '#333';
                bugTitleLabel.innerHTML = 'Bug Title:';
                bugTitleInput.style.borderColor = '#ccc';
                if (bugTitleWarning) {
                    bugTitleWarning.style.display = 'none';
                }
            }
        };
        // Listen for input changes
        bugTitleInput.addEventListener('input', updateBugTitleStyling);
        bugTitleInput.addEventListener('blur', updateBugTitleStyling);
        updateVersionStyling();
        updateBugTitleStyling();
        // Handle ESC key to close the modal
        const handleEscKey = (e) => {
            if (e.key === 'Escape') {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                cancelModal();
            }
        };
        document.addEventListener('keydown', handleEscKey, true);
        const okBtn = content.querySelector('#okBtn');
        const closeBtn = content.querySelector('#closeBtn');
        const cancelBtn = content.querySelector('#cancelBtn');
        if (!okBtn) {
            console.error('BugReportUI: #okBtn not found in modal');
            return;
        }
        // Handle OK button
        okBtn.addEventListener('click', () => {
            // Validate version field - if empty, just update styling and don't submit
            const versionValue = versionInput.value.trim();
            if (!versionValue) {
                updateVersionStyling();
                versionInput.focus();
                return;
            }
            // Validate bug title field - if empty or still placeholder, don't submit
            const bugTitleValue = bugTitleInput.value.trim();
            if (!bugTitleValue || bugTitleValue === bugTitlePlaceholder) {
                updateBugTitleStyling();
                bugTitleInput.focus();
                return;
            }
            const selectedRadio = content.querySelector('input[name="bugTeam"]:checked');
            const selectedTeam = selectedRadio ? selectedRadio.value : null;
            const showStopperCheck = content.querySelector('#showStopperCheck');
            const showStopperValue = showStopperCheck && showStopperCheck.checked ? "1" : "0";
            const isDegradationCheck = content.querySelector('#isDegradationCheck');
            const isDegradationValue = isDegradationCheck && isDegradationCheck.checked ? "Degradation" : "";
            // Get editor content as HTML
            const editorDiv = content.querySelector('#editor');
            const bugDescriptionValue = editorDiv ? editorDiv.innerHTML : "";
            // Use the version value we already validated above
            const manualVersion = versionValue;
            const selection = {
                team: selectedTeam,
                showStopper: showStopperValue,
                isDegradation: isDegradationValue,
                bugTitle: bugTitleValue,
                bugDescription: bugDescriptionValue,
                manualVersion: manualVersion
            };
            this.lastSelectionResult = selection;
            modal.remove();
            document.removeEventListener('keydown', handleEscKey, true);
            resolve(selection);
        });
        if (closeBtn) {
            closeBtn.addEventListener('click', cancelModal);
        }
        if (cancelBtn) {
            cancelBtn.addEventListener('click', cancelModal);
        }
        // Close on background click (also cancels)
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                cancelModal();
            }
        });
    }
    getUserBugInputs(testName, setupName, hasVersion, bugData = null, draftKey = null) {
        return new Promise((resolve) => {
            const modal = this.createModal();
            const content = this.createBugInputForm(testName, setupName, hasVersion, bugData, draftKey);
            modal.appendChild(content);
            document.body.appendChild(modal);
            this.setupModalEventHandlers(modal, content, resolve, hasVersion);
        });
    }
    addButton(onClickCallback) {
        if (this.buttonAdded) return;
        const button = document.createElement("button");
        button.id = "extractDataBtn";
        button.innerText = "🐞";
        button.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center;">
            <span style="font-size: 25px;">🐞</span>
            <span style="font-size: 12px; margin-top: 0.3px;">RM</span>
        </div>
        `;
        Object.assign(button.style, {
            position: "fixed",
            bottom: "20px",
            right: "20px",
            width: "50px",
            height: "50px",
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
