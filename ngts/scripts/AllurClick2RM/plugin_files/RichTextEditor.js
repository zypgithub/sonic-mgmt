class RichTextEditor {
    static initialize(content) {
        const toolbar = content.querySelector('#editorToolbar');
        const editor = content.querySelector('#editor');
        if (!toolbar || !editor) return;
        // Store the last selection from the editor
        let savedSelection = null;
        editor.addEventListener('mouseup', () => {
            const selection = window.getSelection();
            if (selection.rangeCount > 0) {
                savedSelection = selection.getRangeAt(0).cloneRange();
            }
        });
        editor.addEventListener('keyup', () => {
            const selection = window.getSelection();
            if (selection.rangeCount > 0) {
                savedSelection = selection.getRangeAt(0).cloneRange();
            }
        });
        // Color palette - 30 nice colors
        const colors = [
            '#000000', '#424242', '#636363', '#9C9C94', '#CEC6CE', '#EFEFEF',
            '#F7031A', '#FF6900', '#FCB900', '#7BDCB5', '#00D084', '#8ED1FC',
            '#0693E3', '#ABB8C3', '#EB144C', '#F78DA7', '#9900EF', '#FFFFFF',
            '#8B4513', '#D4AF37', '#FFD700', '#ADFF2F', '#32CD32', '#00CED1',
            '#4169E1', '#9370DB', '#FF1493', '#FF69B4', '#FFA500', '#FF6347'
        ];
        // Create color palettes
        const textColorPalette = content.querySelector('#textColorPalette > div');
        const bgColorPalette = content.querySelector('#bgColorPalette > div');
        if (textColorPalette) {
            colors.forEach(color => {
                const colorBox = document.createElement('div');
                colorBox.style.cssText = `
                    width: 24px;
                    height: 24px;
                    background: ${color};
                    border: 1px solid #ddd;
                    border-radius: 3px;
                    cursor: pointer;
                    transition: transform 0.1s;
                `;
                colorBox.title = color;
                colorBox.addEventListener('mouseenter', () => {
                    colorBox.style.transform = 'scale(1.2)';
                    colorBox.style.borderColor = '#333';
                });
                colorBox.addEventListener('mouseleave', () => {
                    colorBox.style.transform = 'scale(1)';
                    colorBox.style.borderColor = '#ddd';
                });
                colorBox.addEventListener('click', () => {
                    editor.focus();
                    // Restore the saved selection
                    if (savedSelection) {
                        const selection = window.getSelection();
                        selection.removeAllRanges();
                        selection.addRange(savedSelection);
                        if (!selection.isCollapsed) {
                            // Has selection - apply color to selected text
                            document.execCommand('foreColor', false, color);
                        } else {
                            // No selection - just apply color for next text to be typed
                            document.execCommand('foreColor', false, color);
                        }
                        // Save the new selection
                        if (selection.rangeCount > 0) {
                            savedSelection = selection.getRangeAt(0).cloneRange();
                        }
                    }
                    content.querySelector('#textColorPalette').style.display = 'none';
                });
                textColorPalette.appendChild(colorBox);
            });
        }
        if (bgColorPalette) {
            colors.forEach(color => {
                const colorBox = document.createElement('div');
                colorBox.style.cssText = `
                    width: 24px;
                    height: 24px;
                    background: ${color};
                    border: 1px solid #ddd;
                    border-radius: 3px;
                    cursor: pointer;
                    transition: transform 0.1s;
                `;
                colorBox.title = color;
                colorBox.addEventListener('mouseenter', () => {
                    colorBox.style.transform = 'scale(1.2)';
                    colorBox.style.borderColor = '#333';
                });
                colorBox.addEventListener('mouseleave', () => {
                    colorBox.style.transform = 'scale(1)';
                    colorBox.style.borderColor = '#ddd';
                });
                colorBox.addEventListener('click', () => {
                    editor.focus();
                    // Restore the saved selection
                    if (savedSelection) {
                        const selection = window.getSelection();
                        selection.removeAllRanges();
                        selection.addRange(savedSelection);
                        if (!selection.isCollapsed) {
                            // Has selection - apply background color to selected text
                            document.execCommand('backColor', false, color);
                        } else {
                            // No selection - just apply background color for next text to be typed
                            document.execCommand('backColor', false, color);
                        }
                        // Save the new selection
                        if (selection.rangeCount > 0) {
                            savedSelection = selection.getRangeAt(0).cloneRange();
                        }
                    }
                    content.querySelector('#bgColorPalette').style.display = 'none';
                });
                bgColorPalette.appendChild(colorBox);
            });
        }
        // Toggle color palette dropdowns
        const textColorBtn = content.querySelector('#textColorBtn');
        const bgColorBtn = content.querySelector('#bgColorBtn');
        const textPalette = content.querySelector('#textColorPalette');
        const bgPalette = content.querySelector('#bgColorPalette');
        if (textColorBtn && textPalette) {
            textColorBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                textPalette.style.display = textPalette.style.display === 'none' ? 'block' : 'none';
                bgPalette.style.display = 'none'; // Close other palette
            });
        }
        if (bgColorBtn && bgPalette) {
            bgColorBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                bgPalette.style.display = bgPalette.style.display === 'none' ? 'block' : 'none';
                textPalette.style.display = 'none'; // Close other palette
            });
        }
        // Close palettes when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#textColorBtn') && !e.target.closest('#textColorPalette')) {
                textPalette.style.display = 'none';
            }
            if (!e.target.closest('#bgColorBtn') && !e.target.closest('#bgColorPalette')) {
                bgPalette.style.display = 'none';
            }
        });
        // Add button click handlers
        toolbar.querySelectorAll('button[data-command]').forEach(button => {
            button.addEventListener('mousedown', (e) => {
                e.preventDefault(); // Prevent losing focus from editor
                const command = button.getAttribute('data-command');
                if (command === 'createLink') {
                    // Save the current selection before opening dialog
                    const selection = window.getSelection();
                    let savedRange = null;
                    let selectedText = '';
                    if (selection.rangeCount > 0) {
                        savedRange = selection.getRangeAt(0).cloneRange();
                        selectedText = savedRange.toString();
                    }
                    // Create custom link dialog
                    const linkDialog = document.createElement('div');
                    linkDialog.style.cssText = `
                        position: fixed;
                        top: 50%;
                        left: 50%;
                        transform: translate(-50%, -50%);
                        background: white;
                        padding: 20px;
                        border-radius: 8px;
                        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                        z-index: 20000;
                        width: 400px;
                    `;
                    linkDialog.innerHTML = `
                        <h3 style="margin: 0 0 15px 0; color: #333;">Insert Link</h3>
                        <div style="margin-bottom: 15px;">
                            <label style="display: block; margin-bottom: 5px; font-weight: bold; color: #555;">Link Text:</label>
                            <input type="text" id="linkText" value="${selectedText}" placeholder="Display text for the link"
                                style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;">
                        </div>
                        <div style="margin-bottom: 20px;">
                            <label style="display: block; margin-bottom: 5px; font-weight: bold; color: #555;">URL:</label>
                            <input type="text" id="linkUrl" placeholder="https://example.com"
                                style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;">
                        </div>
                        <div style="text-align: right;">
                            <button id="linkCancelBtn" style="padding: 8px 16px; margin-right: 10px; background: #ccc; color: black; border: none; border-radius: 4px; cursor: pointer;">Cancel</button>
                            <button id="linkOkBtn" style="padding: 8px 16px; background: #007cba; color: white; border: none; border-radius: 4px; cursor: pointer;">Insert</button>
                        </div>
                    `;
                    // Create backdrop
                    const backdrop = document.createElement('div');
                    backdrop.style.cssText = `
                        position: fixed;
                        top: 0;
                        left: 0;
                        right: 0;
                        bottom: 0;
                        background: rgba(0,0,0,0.5);
                        z-index: 19999;
                    `;
                    document.body.appendChild(backdrop);
                    document.body.appendChild(linkDialog);
                    const linkTextInput = linkDialog.querySelector('#linkText');
                    const linkUrlInput = linkDialog.querySelector('#linkUrl');
                    // Focus the URL input
                    linkUrlInput.focus();
                    // Handle OK button
                    linkDialog.querySelector('#linkOkBtn').addEventListener('click', () => {
                        let url = linkUrlInput.value.trim();
                        const text = linkTextInput.value.trim();
                        if (url) {
                            // Add https:// if no protocol is specified
                            if (!url.match(/^[a-zA-Z]+:\/\//)) {
                                url = 'https://' + url;
                            }
                            editor.focus();
                            // Restore the saved selection
                            if (savedRange) {
                                selection.removeAllRanges();
                                selection.addRange(savedRange);
                            }
                            // Create link element
                            const link = document.createElement('a');
                            link.href = url;
                            link.textContent = text || url;
                            link.target = '_blank';
                            link.style.color = '#007cba';
                            link.style.textDecoration = 'underline';
                            // Delete selected content and insert link
                            savedRange.deleteContents();
                            savedRange.insertNode(link);
                            // Move cursor after the link
                            const newRange = document.createRange();
                            newRange.setStartAfter(link);
                            newRange.collapse(true);
                            selection.removeAllRanges();
                            selection.addRange(newRange);
                        }
                        backdrop.remove();
                        linkDialog.remove();
                        editor.focus();
                    });
                    // Handle Cancel button
                    linkDialog.querySelector('#linkCancelBtn').addEventListener('click', () => {
                        backdrop.remove();
                        linkDialog.remove();
                        editor.focus();
                    });
                    // Handle Enter key in inputs
                    [linkTextInput, linkUrlInput].forEach(input => {
                        input.addEventListener('keydown', (e) => {
                            if (e.key === 'Enter') {
                                e.preventDefault();
                                linkDialog.querySelector('#linkOkBtn').click();
                            } else if (e.key === 'Escape') {
                                e.preventDefault();
                                linkDialog.querySelector('#linkCancelBtn').click();
                            }
                        });
                    });
                 } else if (command === 'code') {
                     RichTextEditor._handleCodeCommand(editor);
                 } else if (command === 'underline') {
                     RichTextEditor._handleUnderlineCommand(editor);
                 } else {
                    document.execCommand(command, false, null);
                }
                // Keep focus on editor
                editor.focus();
            });
            // Hover effect
            button.addEventListener('mouseenter', () => {
                button.style.background = '#e8e8e8';
            });
            button.addEventListener('mouseleave', () => {
                button.style.background = 'white';
            });
        });
        // Add keyboard shortcuts
        editor.addEventListener('keydown', (e) => {
            if (e.ctrlKey || e.metaKey) {
                switch(e.key.toLowerCase()) {
                    case 'b':
                        e.preventDefault();
                        document.execCommand('bold');
                        break;
                    case 'i':
                        e.preventDefault();
                        document.execCommand('italic');
                        break;
                    case 'u':
                        e.preventDefault();
                        RichTextEditor._handleUnderlineCommand(editor);
                        break;
                }
            }
            // Handle Enter key inside code blocks - insert <br> manually
            if (e.key === 'Enter') {
                if (RichTextEditor._handleEnterInCodeBlock(e, editor)) {
                    return;
                }
            }
            // Exit code block with Arrow Right at the end
            if (e.key === 'ArrowRight') {
                RichTextEditor._handleArrowRightInCodeBlock(e, editor);
            }
        });
        // Set initial focus
        editor.focus();
    }
    static _handleCodeCommand(editor) {
        // Toggle code block - if already in code block, exit it (keep text)
        const selection = window.getSelection();
        if (selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);
            let currentNode = range.startContainer;
            // Check if we're already inside a <pre> block
            let existingCodeElement = null;
            let node = currentNode;
            while (node && node !== editor) {
                if (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'PRE') {
                    existingCodeElement = node;
                    break;
                }
                node = node.parentNode;
            }
            if (existingCodeElement) {
                // We're inside a code block - exit it but KEEP the text (without formatting)
                const codeText = existingCodeElement.innerHTML;
                // Convert <br> tags to plain text line breaks for better display
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = codeText;
                const plainText = tempDiv.innerText || tempDiv.textContent;
                const textNode = document.createTextNode(plainText + '\u00A0');
                existingCodeElement.parentNode.replaceChild(textNode, existingCodeElement);
                // Place cursor after the text
                const newRange = document.createRange();
                newRange.setStart(textNode, plainText.length);
                newRange.collapse(true);
                selection.removeAllRanges();
                selection.addRange(newRange);
                editor.focus();
            } else {
                // Not in code block - create a <pre> block (like in the template)
                const selectedText = range.toString();
                // Create a <pre> element that matches the template style
                const pre = document.createElement('pre');
                pre.setAttribute('contenteditable', 'true');
                pre.textContent = selectedText || ' ';
                range.deleteContents();
                range.insertNode(pre);
                // Add line breaks before and after for spacing
                const brBefore = document.createElement('br');
                const brAfter = document.createElement('br');
                if (pre.previousSibling) {
                    pre.parentNode.insertBefore(brBefore, pre);
                }
                if (pre.nextSibling) {
                    pre.parentNode.insertBefore(brAfter, pre.nextSibling);
                } else {
                    pre.parentNode.appendChild(brAfter);
                }
                // Move cursor inside the pre element
                const newRange = document.createRange();
                newRange.selectNodeContents(pre);
                newRange.collapse(false); // Collapse to end
                selection.removeAllRanges();
                selection.addRange(newRange);
                // Focus the pre element
                pre.focus();
            }
        }
    }
    static _handleUnderlineCommand(editor) {
        // Check if we're inside an <ins> tag (from template) which needs special handling
        const selection = window.getSelection();
        if (selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);
            let insElement = null;
            let currentNode = range.commonAncestorContainer;
            // Look for <ins> tag in parent hierarchy
            while (currentNode && currentNode !== editor) {
                if (currentNode.nodeType === Node.ELEMENT_NODE && currentNode.tagName === 'INS') {
                    insElement = currentNode;
                    break;
                }
                currentNode = currentNode.parentNode;
            }
            if (insElement && range.collapsed) {
                // We're inside an <ins> tag with just cursor (no selection)
                // Split the <ins> tag at cursor position and move cursor outside
                // Get all parent formatting elements between cursor and <ins>
                const formattingElements = [];
                let node = range.startContainer;
                while (node && node !== insElement) {
                    if (node.nodeType === Node.ELEMENT_NODE &&
                        (node.tagName === 'STRONG' || node.tagName === 'B' ||
                         node.tagName === 'EM' || node.tagName === 'I')) {
                        formattingElements.push(node.tagName);
                    }
                    node = node.parentNode;
                }
                // Create a space outside the <ins> tag with preserved formatting
                let newElement = document.createTextNode('\u200B'); // zero-width space
                // Re-apply formatting elements (like <strong>) but not underline
                for (let i = formattingElements.length - 1; i >= 0; i--) {
                    const wrapper = document.createElement(formattingElements[i]);
                    wrapper.appendChild(newElement);
                    newElement = wrapper;
                }
                // Insert after the <ins> element
                if (insElement.nextSibling) {
                    insElement.parentNode.insertBefore(newElement, insElement.nextSibling);
                } else {
                    insElement.parentNode.appendChild(newElement);
                }
                // Move cursor to the new position
                const newRange = document.createRange();
                const textNode = newElement.nodeType === Node.TEXT_NODE ? newElement : newElement.firstChild;
                newRange.setStart(textNode, 1);
                newRange.collapse(true);
                selection.removeAllRanges();
                selection.addRange(newRange);
            } else {
                // Not in <ins>, or has selection - use standard command
                document.execCommand('underline');
            }
        } else {
            document.execCommand('underline');
        }
    }
    static _handleEnterInCodeBlock(e, editor) {
        const selection = window.getSelection();
        if (selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);
            const currentNode = range.startContainer;
            // Check if we're inside a <pre> element
            let codeElement = null;
            let node = currentNode;
            while (node && node !== editor) {
                if (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'PRE') {
                    codeElement = node;
                    break;
                }
                node = node.parentNode;
            }
            if (codeElement) {
                // Prevent default Enter behavior and insert <br> manually
                e.preventDefault();
                e.stopPropagation();
                // Insert a line break and a zero-width space to keep cursor in the right place
                const br = document.createElement('br');
                range.deleteContents();
                range.insertNode(br);
                // Add a zero-width space after the br to ensure cursor stays inside
                const zeroWidthSpace = document.createTextNode('\u200B');
                if (br.nextSibling) {
                    br.parentNode.insertBefore(zeroWidthSpace, br.nextSibling);
                } else {
                    br.parentNode.appendChild(zeroWidthSpace);
                }
                // Move cursor after the <br> and zero-width space
                range.setStartAfter(zeroWidthSpace);
                range.collapse(true);
                selection.removeAllRanges();
                selection.addRange(range);
                // Ensure focus stays on the code element
                codeElement.focus();
                return true;
            }
        }
        return false;
    }
    static _handleArrowRightInCodeBlock(e, editor) {
        const selection = window.getSelection();
        if (selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);
            const currentNode = range.startContainer;
            // Check if we're inside a <pre> element
            let codeElement = null;
            let node = currentNode;
            while (node && node !== editor) {
                if (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'PRE') {
                    codeElement = node;
                    break;
                }
                node = node.parentNode;
            }
            if (codeElement) {
                // Check if cursor is at the end
                const textContent = codeElement.textContent || '';
                let cursorOffset = 0;
                if (range.startContainer.nodeType === Node.TEXT_NODE) {
                    cursorOffset = range.startOffset;
                    // Check if we're at the end of the text
                    let tempNode = range.startContainer;
                    while (tempNode && tempNode !== codeElement) {
                        if (tempNode.previousSibling) {
                            let prev = tempNode.previousSibling;
                            while (prev) {
                                if (prev.nodeType === Node.TEXT_NODE) {
                                    cursorOffset += prev.textContent.length;
                                }
                                prev = prev.previousSibling;
                            }
                        }
                        tempNode = tempNode.parentNode;
                    }
                }
                const atEnd = cursorOffset >= textContent.length;
                if (atEnd) {
                    e.preventDefault();
                    // Exit code block - move cursor after it
                    const newRange = document.createRange();
                    if (codeElement.nextSibling) {
                        if (codeElement.nextSibling.nodeType === Node.TEXT_NODE && codeElement.nextSibling.textContent === '\u00A0') {
                            newRange.setStartAfter(codeElement.nextSibling);
                        } else {
                            newRange.setStartAfter(codeElement);
                        }
                    } else {
                        newRange.setStartAfter(codeElement);
                    }
                    newRange.collapse(true);
                    selection.removeAllRanges();
                    selection.addRange(newRange);
                    editor.focus();
                }
            }
        }
    }
}
