class UsernameManager {
      constructor() {
          this.STORAGE_KEY = "bug_plugin_username";
          this.username = "";
      }
      // Get the stored username from localStorage
      getStoredUsername() {
          try {
              return localStorage.getItem(this.STORAGE_KEY) || "";
          } catch (error) {
              console.error("Failed to read username from storage:", error);
              return "";
          }
      }
      // Save username to localStorage
      saveUsername(username) {
          try {
              localStorage.setItem(this.STORAGE_KEY, username);
              this.username = username;
              return true;
          } catch (error) {
              console.error("Failed to save username to storage:", error);
              return false;
          }
      }
      // Prompt user for username if not set
      async promptForUsername() {
          return new Promise((resolve) => {
              const modal = document.createElement('div');
              modal.style.cssText = `
                  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                  background: rgba(0,0,0,0.5); z-index: 20000;
                  display: flex; align-items: center; justify-content: center;
              `;
              const box = document.createElement('div');
              box.style.cssText = `
                  background: white; padding: 30px; border-radius: 10px;
                  max-width: 500px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                  font-family: Arial, sans-serif;
              `;
              box.innerHTML = `
                  <h3 style="margin: 0 0 15px 0; color: #333;">Welcome to Bug Reporter</h3>
                  <p style="color: #666; margin-bottom: 20px;">
                      Please enter your username. This will be saved and used for all future bug reports.
                  </p>
                  <div style="margin-bottom: 20px;">
                      <label style="display: block; margin-bottom: 8px; font-weight: bold; color: #333;">
                          Your Username: <span style="color: #d32f2f;">*</span>
                      </label>
                      <input type="text" id="usernameInput" placeholder="Enter your username"
                          style="width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;">
                      <small style="color: #999; display: block; margin-top: 4px;">
                          Example: jdoe, john.doe
                      </small>
                  </div>
                  <div style="text-align: right;">
                      <button id="usernameCancelBtn" style="
                          padding: 10px 20px; margin-right: 10px; background: #ccc;
                          color: black; border: none; border-radius: 4px; cursor: pointer;
                      ">Cancel</button>
                      <button id="usernameOkBtn" style="
                          padding: 10px 20px; background: #4CAF50;
                          color: white; border: none; border-radius: 4px; cursor: pointer;
                      ">Save</button>
                  </div>
              `;
              modal.appendChild(box);
              document.body.appendChild(modal);
              const input = box.querySelector('#usernameInput');
              const okBtn = box.querySelector('#usernameOkBtn');
              const cancelBtn = box.querySelector('#usernameCancelBtn');
              // Focus the input
              setTimeout(() => input.focus(), 100);
              // Handle OK button
              okBtn.addEventListener('click', () => {
                  const username = input.value.trim();
                  if (username) {
                      modal.remove();
                      resolve(username);
                  } else {
                      input.style.borderColor = '#d32f2f';
                      input.placeholder = 'Username is required!';
                  }
              });
              // Handle Cancel button
              cancelBtn.addEventListener('click', () => {
                  modal.remove();
                  resolve(null);
              });
              // Handle Enter key
              input.addEventListener('keydown', (e) => {
                  if (e.key === 'Enter') {
                      e.preventDefault();
                      okBtn.click();
                  } else if (e.key === 'Escape') {
                      e.preventDefault();
                      cancelBtn.click();
                  }
              });
              // Remove red border when user starts typing
              input.addEventListener('input', () => {
                  input.style.borderColor = '#ccc';
              });
          });
      }
      // Ensure username is set before proceeding
      async ensureUsername() {
          // Try to get stored username
          this.username = this.getStoredUsername();
          // If no username, prompt the user
          if (!this.username) {
              const username = await this.promptForUsername();
              if (!username) {
                  // User cancelled - return null to exit silently
                  return null;
              }
              this.saveUsername(username);
          }
          return this.username;
      }
      // Get the current username (call after ensureUsername)
      getUsername() {
          return this.username;
      }
  }
  