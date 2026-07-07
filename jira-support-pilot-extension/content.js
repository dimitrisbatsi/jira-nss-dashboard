// Jira Support Pilot - Content Script
(function () {
  let shadowRoot = null;
  let currentIssueKey = '';
  let currentIssueData = null;
  let cachedCannedResponses = [];
  let credentials = null;
  let currentUserAccountId = null;
  let currentIsEpic = false;

  // Poll for URL changes (Jira is an SPA)
  let lastUrl = location.href;
  setInterval(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      handleUrlChange();
    }
  }, 1000);

  // Initialize Extension UI
  init();

  async function init() {
    // Load credentials from storage
    credentials = await getCredentials();
    if (credentials) {
      await fetchCurrentUser();
    }
    
    // Setup Shadow DOM Container
    const host = document.createElement('div');
    host.id = 'support-pilot-shadow-host';
    host.style.position = 'fixed';
    host.style.top = '0';
    host.style.right = '0';
    host.style.width = '0';
    host.style.height = '0';
    host.style.zIndex = '2147483647';
    host.style.pointerEvents = 'none';
    document.body.appendChild(host);

    shadowRoot = host.attachShadow({ mode: 'open' });

    // Inject sidebar CSS
    const cssUrl = chrome.runtime.getURL('sidebar.css');
    const linkElement = document.createElement('link');
    linkElement.rel = 'stylesheet';
    linkElement.href = cssUrl;
    shadowRoot.appendChild(linkElement);

    // Fetch and inject sidebar HTML
    const htmlUrl = chrome.runtime.getURL('sidebar.html');
    const response = await fetch(htmlUrl);
    const htmlText = await response.text();
    
    const container = document.createElement('div');
    container.innerHTML = htmlText;
    shadowRoot.appendChild(container);

    // Prevent Jira keyboard shortcuts from triggering when typing in our sidebar inputs
    container.addEventListener('keydown', (e) => {
      e.stopPropagation();
    });
    container.addEventListener('keyup', (e) => {
      e.stopPropagation();
    });
    container.addEventListener('keypress', (e) => {
      e.stopPropagation();
    });

    // Prevent Jira from hijacking clicks and focus trap inside the sidebar
    const stopEvents = ['mousedown', 'mouseup', 'click', 'pointerdown', 'pointerup', 'focusin', 'focusout'];
    stopEvents.forEach(evtName => {
      container.addEventListener(evtName, (e) => {
        e.stopPropagation();
      });
    });

    // Load Canned Responses
    await loadCannedResponses();

    // Event Bindings
    setupEventHandlers();

    // Initial check
    handleUrlChange();
  }

  // Load parsed canned responses JSON via background worker (bypasses page CSP)
  function loadCannedResponses() {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ action: 'LOAD_CANNED_RESPONSES' }, (response) => {
          if (response && response.success) {
            cachedCannedResponses = response.data;
            populateCannedSelect();
            resolve(true);
          } else {
            console.error('Error loading canned responses from background:', response ? response.error : 'No response');
            resolve(false);
          }
        });
      } catch (e) {
        console.error('Error sending load canned responses message:', e);
        resolve(false);
      }
    });
  }

  // Retrieve Email and API Token from storage
  function getCredentials() {
    return new Promise((resolve) => {
      chrome.storage.local.get(['jiraEmail', 'jiraToken'], (result) => {
        if (result.jiraEmail && result.jiraToken) {
          resolve({ email: result.jiraEmail, token: result.jiraToken });
        } else {
          resolve(null);
        }
      });
    });
  }

  // Fetch current user details from JIRA to obtain accountId for auto-assigning
  async function fetchCurrentUser() {
    if (!credentials) return;
    try {
      const res = await callJiraApi('/rest/api/3/myself', 'GET');
      if (res.success && res.data) {
        currentUserAccountId = res.data.accountId;
      }
    } catch (e) {
      console.error('Error fetching current user:', e);
    }
  }

  // Transform a native select element into a beautiful custom styled dropdown widget
  function transformSelectToCustom(selectEl) {
    if (!selectEl || selectEl.dataset.customized === 'true') return;
    selectEl.dataset.customized = 'true';
    
    // Hide original native select
    selectEl.style.display = 'none';
    
    // Create wrapper container
    const wrapper = document.createElement('div');
    wrapper.className = 'pilot-custom-select';
    
    // Create trigger display
    const trigger = document.createElement('div');
    trigger.className = 'pilot-custom-select-trigger';
    trigger.textContent = selectEl.options[selectEl.selectedIndex]?.text || 'Select...';
    wrapper.appendChild(trigger);
    
    // Create options container
    const optionsContainer = document.createElement('div');
    optionsContainer.className = 'pilot-custom-select-options hide';
    wrapper.appendChild(optionsContainer);
    
    // Function to rebuild options list dynamically
    function rebuildOptions() {
      optionsContainer.innerHTML = '';
      Array.from(selectEl.options).forEach(opt => {
        const item = document.createElement('div');
        item.className = 'pilot-custom-select-option';
        if (opt.value === selectEl.value) {
          item.classList.add('selected');
        }
        item.textContent = opt.text;
        item.dataset.value = opt.value;
        
        item.addEventListener('click', (e) => {
          e.stopPropagation();
          selectEl.value = opt.value;
          trigger.textContent = opt.text;
          
          optionsContainer.querySelectorAll('.pilot-custom-select-option').forEach(el => el.classList.remove('selected'));
          item.classList.add('selected');
          
          optionsContainer.classList.add('hide');
          
          // Trigger change event on native select
          const event = new Event('change', { bubbles: true });
          selectEl.dispatchEvent(event);
        });
        
        optionsContainer.appendChild(item);
      });
    }
    
    // Initial build
    rebuildOptions();
    
    // Toggle dropdown
    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      // Close other open custom dropdowns first
      shadowRoot.querySelectorAll('.pilot-custom-select-options').forEach(el => {
        if (el !== optionsContainer) el.classList.add('hide');
      });
      rebuildOptions();
      optionsContainer.classList.toggle('hide');
    });
    
    // Insert wrapper next to original select
    selectEl.parentNode.insertBefore(wrapper, selectEl.nextSibling);
    
    // Sync helper
    selectEl.updateCustomDisplay = () => {
      trigger.textContent = selectEl.options[selectEl.selectedIndex]?.text || 'Select...';
      rebuildOptions();
    };
  }

  // Set up click handlers and tabs inside shadow root
  function setupEventHandlers() {
    // Convert native select elements into custom dropdown elements
    shadowRoot.querySelectorAll('select').forEach(transformSelectToCustom);
    
    // Close custom selects on outside shadow DOM click
    shadowRoot.addEventListener('click', () => {
      shadowRoot.querySelectorAll('.pilot-custom-select-options').forEach(el => el.classList.add('hide'));
    });

    const toggleBtn = shadowRoot.getElementById('support-pilot-toggle');
    const closeBtn = shadowRoot.getElementById('support-pilot-close');
    const sidebar = shadowRoot.getElementById('support-pilot-container');

    // Toggle Panel
    toggleBtn.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      if (sidebar.classList.contains('open')) {
        refreshActiveIssue();
      }
    });

    closeBtn.addEventListener('click', () => {
      sidebar.classList.remove('open');
    });

    // Refresh Button Handler
    const refreshBtn = shadowRoot.getElementById('support-pilot-refresh');
    refreshBtn.addEventListener('click', () => {
      refreshBtn.style.transform = 'rotate(360deg)';
      refreshActiveIssue();
      setTimeout(() => {
        refreshBtn.style.transform = '';
      }, 500);
    });

    // Tab Switching
    const tabButtons = shadowRoot.querySelectorAll('.pilot-tab-btn');
    tabButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        tabButtons.forEach(b => b.classList.remove('active'));
        shadowRoot.querySelectorAll('.pilot-tab-content').forEach(c => c.classList.remove('active'));
        
        btn.classList.add('active');
        shadowRoot.getElementById(btn.dataset.tab).classList.add('active');
      });
    });

    // Settings Toggle Password Visibility
    const pwToggle = shadowRoot.getElementById('settings-token-toggle');
    const tokenInput = shadowRoot.getElementById('settings-token');
    pwToggle.addEventListener('click', () => {
      if (tokenInput.type === 'password') {
        tokenInput.type = 'text';
        pwToggle.textContent = '🔒';
      } else {
        tokenInput.type = 'password';
        pwToggle.textContent = '👁️';
      }
    });

    // Settings Save Button
    const saveSettingsBtn = shadowRoot.getElementById('settings-save-btn');
    saveSettingsBtn.addEventListener('click', () => {
      const email = shadowRoot.getElementById('settings-email').value.trim();
      const token = shadowRoot.getElementById('settings-token').value.trim();
      const statusDiv = shadowRoot.getElementById('settings-status');

      if (!email || !token) {
        showStatus(statusDiv, 'Please fill in both Email and Jira Token.', 'error');
        return;
      }

      chrome.storage.local.set({ jiraEmail: email, jiraToken: token }, async () => {
        credentials = { email, token };
        showStatus(statusDiv, 'Settings saved successfully!', 'success');
        await fetchCurrentUser();
        refreshActiveIssue();
      });
    });

    // Expandable settings instructions toggle
    const accHeader = shadowRoot.getElementById('instructions-accordion-header');
    const accContent = shadowRoot.getElementById('instructions-accordion-content');
    const accIcon = accHeader.querySelector('.pilot-accordion-icon');
    
    accHeader.addEventListener('click', (e) => {
      e.stopPropagation();
      const isHidden = accContent.classList.toggle('hide');
      accIcon.textContent = isHidden ? '▶' : '▼';
    });

    // Load credentials in inputs
    if (credentials) {
      shadowRoot.getElementById('settings-email').value = credentials.email;
      shadowRoot.getElementById('settings-token').value = credentials.token;
    }

    // Chat Canned Selection Changed & Real-time Live Markdown Preview
    const cannedSelect = shadowRoot.getElementById('chat-canned-select');
    const previewArea = shadowRoot.getElementById('chat-text-preview');
    const markdownPreview = shadowRoot.getElementById('chat-markdown-preview');

    cannedSelect.addEventListener('change', () => {
      const selectedIndex = cannedSelect.value;
      
      if (selectedIndex === '' || !cachedCannedResponses[selectedIndex]) {
        previewArea.value = '';
        markdownPreview.innerHTML = '<em>Select a template or write a custom message to see preview...</em>';
        return;
      }
      
      const rawTemplate = cachedCannedResponses[selectedIndex].body;
      const parsedText = applyTemplatePlaceholders(rawTemplate);
      previewArea.value = parsedText;
      markdownPreview.innerHTML = renderMarkdownToHtml(parsedText);
    });

    // Update markdown preview in real-time as user edits textarea
    previewArea.addEventListener('input', () => {
      markdownPreview.innerHTML = renderMarkdownToHtml(previewArea.value);
    });

    // Chat Copy & Insert Action
    const chatInsertBtn = shadowRoot.getElementById('chat-insert-btn');
    chatInsertBtn.addEventListener('click', async () => {
      const text = shadowRoot.getElementById('chat-text-preview').value.trim();
      const statusDiv = shadowRoot.getElementById('chat-status');
      
      if (!text) {
        showStatus(statusDiv, 'Please select or enter comment text.', 'error');
        return;
      }

      try {
        // 1. Copy both HTML (rendered) and plain text to clipboard
        const htmlContent = renderMarkdownToHtml(text);
        try {
          const blobHtml = new Blob([htmlContent], { type: 'text/html' });
          const blobText = new Blob([text], { type: 'text/plain' });
          await navigator.clipboard.write([
            new ClipboardItem({
              'text/html': blobHtml,
              'text/plain': blobText
            })
          ]);
        } catch (clipErr) {
          console.warn('ClipboardItem write failed, falling back to plain writeText...', clipErr);
          await navigator.clipboard.writeText(text);
        }
        
        // 2. Try inserting into active JIRA editor
        const inserted = insertTextIntoActiveJiraEditor(text);
        if (inserted) {
          showStatus(statusDiv, 'Copied to clipboard & inserted into JIRA editor!', 'success');
        } else {
          showStatus(statusDiv, 'Copied to clipboard! (Please click on JIRA editor and press Ctrl+V)', 'info');
        }
      } catch (err) {
        showStatus(statusDiv, `Clipboard error: ${err.message}`, 'error');
      }
    });

    // Chat Submit Action (Send Direct Comment)
    const chatSubmitBtn = shadowRoot.getElementById('chat-submit-btn');
    chatSubmitBtn.addEventListener('click', async () => {
      const text = shadowRoot.getElementById('chat-text-preview').value.trim();
      const statusDiv = shadowRoot.getElementById('chat-status');
      
      if (!credentials) {
        showStatus(statusDiv, 'Please configure your Jira credentials in settings first.', 'error');
        return;
      }
      if (!text) {
        showStatus(statusDiv, 'Please select or enter comment text.', 'error');
        return;
      }
      if (!currentIssueKey) {
        showStatus(statusDiv, 'No active Jira issue found.', 'error');
        return;
      }

      chatSubmitBtn.disabled = true;
      showStatus(statusDiv, 'Sending standard comment to Jira...', 'info');

      /*
      // FUTURE REFERENCE: The old mechanism that posted comments with service account properties
      if (currentIsEpic) {
        showStatus(statusDiv, 'Sending external comment to Epic...', 'info');
        try {
          const res = await callJiraApi(`/rest/api/3/issue/${currentIssueKey}/comment`, 'POST', {
            body: {
              type: 'doc',
              version: 1,
              content: [
                {
                  type: 'paragraph',
                  content: [
                    {
                      type: 'text',
                      text: text
                    }
                  ]
                }
              ]
            },
            properties: [
              {
                key: 'IsPublished',
                value: {
                  value: 'true'
                }
              },
              {
                key: 'AuthorEmail',
                value: {
                  value: 'ExternalCommunicationAccount'
                }
              },
              {
                key: 'AuthorNickname',
                value: {
                  value: 'ExternalCommunicationAccount'
                }
              }
            ]
          });

          if (res.success) {
            showStatus(statusDiv, 'External comment posted successfully!', 'success');
            shadowRoot.getElementById('chat-text-preview').value = '';
            cannedSelect.value = '';
          } else {
            showStatus(statusDiv, `Failed: ${res.error}`, 'error');
          }
        } catch (err) {
          showStatus(statusDiv, `Error: ${err.message}`, 'error');
        } finally {
          chatSubmitBtn.disabled = false;
        }
      } else {
      */
      try {
        // We POST a standard JIRA comment on the active issue (both Epic and standard issues)
        const res = await callJiraApi(`/rest/api/3/issue/${currentIssueKey}/comment`, 'POST', {
          body: convertTextToAdf(text)
        });

        if (res.success) {
          showStatus(statusDiv, 'Standard comment added successfully!', 'success');
          shadowRoot.getElementById('chat-text-preview').value = '';
          cannedSelect.value = '';
        } else {
          showStatus(statusDiv, `Failed: ${res.error}`, 'error');
        }
      } catch (err) {
        showStatus(statusDiv, `Error: ${err.message}`, 'error');
      } finally {
        chatSubmitBtn.disabled = false;
      }
      /*
      }
      */
    });

    // Time Log Submit Action
    const timeSubmitBtn = shadowRoot.getElementById('time-submit-btn');
    timeSubmitBtn.addEventListener('click', async () => {
      const childSelect = shadowRoot.getElementById('time-child-select');
      const selectedChildKey = childSelect.value;
      
      const hoursVal = parseInt(shadowRoot.getElementById('time-hours').value, 10) || 0;
      const minutesVal = parseInt(shadowRoot.getElementById('time-minutes').value, 10) || 0;
      const comment = shadowRoot.getElementById('time-comment').value.trim();
      const statusDiv = shadowRoot.getElementById('time-status');

      if (!credentials) {
        showStatus(statusDiv, 'Please configure your Jira credentials in settings first.', 'error');
        return;
      }
      if (!selectedChildKey) {
        showStatus(statusDiv, 'Please select a child Service / Task to log hours to.', 'error');
        return;
      }
      if (hoursVal === 0 && minutesVal === 0) {
        showStatus(statusDiv, 'Please enter hours or minutes (e.g. 1h or 30m).', 'error');
        return;
      }

      // Format combined duration string for Jira
      let duration = '';
      if (hoursVal > 0 && minutesVal > 0) {
        duration = `${hoursVal}h ${minutesVal}m`;
      } else if (hoursVal > 0) {
        duration = `${hoursVal}h`;
      } else {
        duration = `${minutesVal}m`;
      }

      timeSubmitBtn.disabled = true;
      showStatus(statusDiv, 'Logging hours in JIRA... (Step 1/3: Creating Time Entry)', 'info');

      try {
        // Step 1: Create the Sub-task
        const projKey = selectedChildKey.split('-')[0];
        
        // Inherited fields from currentIssueData
        let compArray = [];
        if (currentIssueData && currentIssueData.fields.components && currentIssueData.fields.components.length > 0) {
          compArray = [ { id: currentIssueData.fields.components[0].id } ];
        }
        
        let partnerVal = null;
        let lspVal = null;
        if (currentIssueData) {
          partnerVal = currentIssueData.fields.customfield_11180 || null;
          lspVal = currentIssueData.fields.customfield_11183 || null;
        }

        const selectedTimeType = shadowRoot.getElementById('time-type-select').value;
        const selectedChargeType = shadowRoot.getElementById('time-charge-select').value;

        const createSubtaskPayload = {
          fields: {
            project: { key: projKey },
            parent: { key: selectedChildKey },
            summary: comment || 'Time Entry via Support Pilot',
            issuetype: { name: 'Time Type' }, // Set sub-task type to "Time Type"
            customfield_10553: { id: selectedTimeType }, // Time Types
            customfield_10193: { value: selectedChargeType } // Charge Type
          }
        };

        if (compArray.length > 0) {
          createSubtaskPayload.fields.components = compArray;
        }
        if (partnerVal) {
          createSubtaskPayload.fields.customfield_11180 = partnerVal;
        }
        if (lspVal) {
          createSubtaskPayload.fields.customfield_11183 = lspVal;
        }
        if (currentUserAccountId) {
          createSubtaskPayload.fields.assignee = { accountId: currentUserAccountId };
        }

        const subtaskRes = await callJiraApi('/rest/api/3/issue', 'POST', createSubtaskPayload);

        if (!subtaskRes.success) {
          throw new Error(`Failed to create sub-task: ${subtaskRes.error}`);
        }

        const newSubtaskKey = subtaskRes.data.key;
        showStatus(statusDiv, `Time entry created (${newSubtaskKey}). Transitioning... (Step 2/3)`, 'info');

        // Step 2: Transition sub-task status to "Time Entered"
        const transitionsRes = await callJiraApi(`/rest/api/3/issue/${newSubtaskKey}/transitions`, 'GET');
        if (!transitionsRes.success) {
          throw new Error(`Failed to fetch transitions: ${transitionsRes.error}`);
        }

        const transition = transitionsRes.data.transitions.find(t => {
          const nameLower = t.name.toLowerCase();
          const toNameLower = (t.to && t.to.name) ? t.to.name.toLowerCase() : '';
          return nameLower.includes('time entered') || 
                 nameLower.includes('time-entered') || 
                 nameLower.includes('add time') ||
                 toNameLower.includes('time entered') || 
                 toNameLower.includes('time-entered') ||
                 toNameLower.includes('timeentered');
        });

        if (transition) {
          const transitionRes = await callJiraApi(`/rest/api/3/issue/${newSubtaskKey}/transitions`, 'POST', {
            transition: { id: transition.id }
          });
          if (!transitionRes.success) {
            console.warn('Transition failed, attempting to post worklog anyway...', transitionRes.error);
          }
        } else {
          const avail = transitionsRes.data.transitions.map(t => `${t.name} (to: ${t.to ? t.to.name : 'unknown'})`).join(', ');
          console.warn(`Could not find transition leading to "Time Entered". Available transitions: ${avail}`);
        }

        // Step 3: Add the Worklog
        showStatus(statusDiv, 'Adding worklog duration... (Step 3/3)', 'info');
        const worklogPayload = {
          timeSpent: duration,
          comment: convertTextToAdf(comment || 'Time Entry via Support Pilot')
        };

        const worklogRes = await callJiraApi(`/rest/api/3/issue/${newSubtaskKey}/worklog`, 'POST', worklogPayload);

        if (worklogRes.success) {
          showStatus(statusDiv, `Hours successfully logged on child ${selectedChildKey}!`, 'success');
          shadowRoot.getElementById('time-hours').value = '';
          shadowRoot.getElementById('time-minutes').value = '';
          shadowRoot.getElementById('time-comment').value = '';
        } else {
          throw new Error(`Failed to add worklog: ${worklogRes.error}`);
        }

      } catch (err) {
        showStatus(statusDiv, err.message, 'error');
      } finally {
        timeSubmitBtn.disabled = false;
      }
    });

    // Create Child Service/Task Button Helper
    const createChildBtn = shadowRoot.getElementById('time-create-child');
    createChildBtn.addEventListener('click', async () => {
      const statusDiv = shadowRoot.getElementById('time-status');
      if (!currentIssueKey || !currentIssueData) return;

      createChildBtn.disabled = true;
      showStatus(statusDiv, 'Creating child issue in Jira...', 'info');

      try {
        const projKey = currentIssueKey.split('-')[0];
        
        // Inherit Component
        let compArray = [];
        if (currentIssueData.fields.components && currentIssueData.fields.components.length > 0) {
          compArray = [ { id: currentIssueData.fields.components[0].id } ];
        }

        const isTaskSpace = ['KAS', 'INTERNAL'].includes(projKey.toUpperCase()); // add task-specific keys
        const childTypeName = isTaskSpace ? 'Task' : 'Services (Αίτημα Υπηρεσιών)';

        const payload = {
          fields: {
            project: { key: projKey },
            summary: `Service: ${currentIssueData.fields.summary}`,
            description: {
              type: 'doc',
              version: 1,
              content: [
                {
                  type: 'paragraph',
                  content: [
                    {
                      type: 'text',
                      text: 'Created automatically by Jira Support Pilot.'
                    }
                  ]
                }
              ]
            },
            issuetype: { name: childTypeName },
            parent: { key: currentIssueKey } // creates child link
          }
        };

        if (compArray.length > 0) {
          payload.fields.components = compArray;
        }

        const res = await callJiraApi('/rest/api/3/issue', 'POST', payload);
        if (res.success) {
          showStatus(statusDiv, `Child ${childTypeName} created: ${res.data.key}!`, 'success');
          // Reload children dropdown
          fetchAndPopulateChildren(currentIssueKey);
        } else {
          showStatus(statusDiv, `Failed: ${res.error}`, 'error');
        }
      } catch (err) {
        showStatus(statusDiv, err.message, 'error');
      } finally {
        createChildBtn.disabled = false;
      }
    });
  }

  // Handle URL updates and refresh issue info
  function handleUrlChange() {
    let key = '';
    
    // 1. Try matching browse path (e.g. /browse/PYLCOM-123)
    const pathMatch = location.pathname.match(/\/browse\/([A-Za-z]+-[0-9]+)/);
    if (pathMatch) {
      key = pathMatch[1];
    } else {
      // 2. Try matching query parameter selectedIssue (e.g. ?selectedIssue=PYLCOM-123 on boards/popovers)
      const urlParams = new URLSearchParams(location.search);
      const selectedIssue = urlParams.get('selectedIssue');
      if (selectedIssue && selectedIssue.match(/^[A-Za-z]+-[0-9]+$/)) {
        key = selectedIssue;
      }
    }

    if (key && key !== currentIssueKey) {
      currentIssueKey = key;
      currentIssueData = null;
      resetUI();
      
      const sidebar = supportPilotOpenState() ? shadowRoot.getElementById('support-pilot-container') : null;
      if (sidebar && sidebar.classList.contains('open')) {
        refreshActiveIssue();
      }
    } else if (!key) {
      currentIssueKey = '';
      currentIssueData = null;
      resetUI();
    }
  }

  // Helper to safely check if container exists
  function supportPilotOpenState() {
    const el = shadowRoot ? shadowRoot.getElementById('support-pilot-container') : null;
    return el && el.classList.contains('open');
  }

  function resetUI() {
    shadowRoot.getElementById('time-issue-key').textContent = currentIssueKey || 'No Active Issue';
    shadowRoot.getElementById('time-issue-summary').textContent = '-';
    shadowRoot.getElementById('time-issue-partner').textContent = '-';
    shadowRoot.getElementById('time-issue-lsp').textContent = '-';
    shadowRoot.getElementById('time-default-component').textContent = '-';
    
    shadowRoot.getElementById('chat-issue-key').textContent = currentIssueKey || 'No Active Issue';
    shadowRoot.getElementById('chat-issue-summary').textContent = '-';
    
    // Clear selections
    const childSelect = shadowRoot.getElementById('time-child-select');
    childSelect.innerHTML = '<option value="">Choose child...</option>';
    if (childSelect.updateCustomDisplay) childSelect.updateCustomDisplay();
    
    shadowRoot.getElementById('time-create-child').classList.add('hide');
  }

  // Formatting helper for custom fields that might be objects
  function formatJiraField(val, fallback = '-') {
    if (!val) return fallback;
    if (typeof val === 'object') {
      return val.value || val.name || fallback;
    }
    return val;
  }

  // Fetch JIRA ticket details and populate UI
  async function refreshActiveIssue() {
    if (!currentIssueKey) return;
    if (!credentials) {
      showStatus(shadowRoot.getElementById('time-status'), 'Credentials not configured. Go to Settings.', 'error');
      return;
    }

    try {
      const res = await callJiraApi(`/rest/api/3/issue/${currentIssueKey}`, 'GET');
      if (res.success) {
        currentIssueData = res.data;
        
        // Populate UI Cards
        const summary = currentIssueData.fields.summary || '-';
        const partner = formatJiraField(currentIssueData.fields.customfield_11180);
        const lsp = formatJiraField(currentIssueData.fields.customfield_11183);
        const component = currentIssueData.fields.components && currentIssueData.fields.components.length > 0 
          ? currentIssueData.fields.components[0].name 
          : 'None';

        shadowRoot.getElementById('time-issue-key').textContent = currentIssueKey;
        shadowRoot.getElementById('time-issue-summary').textContent = summary;
        shadowRoot.getElementById('time-issue-partner').textContent = partner;
        shadowRoot.getElementById('time-issue-lsp').textContent = lsp;
        shadowRoot.getElementById('time-default-component').textContent = component;

        shadowRoot.getElementById('chat-issue-key').textContent = currentIssueKey;
        shadowRoot.getElementById('chat-issue-summary').textContent = summary;

        // Detect if active ticket is Epic and update button labels
        const issueTypeObj = currentIssueData.fields.issuetype;
        const issueTypeName = issueTypeObj.name.toLowerCase();
        currentIsEpic = issueTypeName.includes('epic') || (typeof issueTypeObj.hierarchyLevel === 'number' && issueTypeObj.hierarchyLevel > 0);
        
        const chatSubmitBtn = shadowRoot.getElementById('chat-submit-btn');
        if (currentIsEpic) {
          chatSubmitBtn.textContent = '💬 Send Direct Comment (as yourself)';
        } else {
          chatSubmitBtn.textContent = '💬 Send Standard Comment (as yourself)';
        }

        // Load Canned Select Options
        populateCannedSelect();

        // Load Children List
        await fetchAndPopulateChildren(currentIssueKey);
      } else {
        console.error('Failed to load issue details:', res.error);
      }
    } catch (e) {
      console.error('Error fetching issue:', e);
    }
  }

  // Populate Tab 2 Canned messages dropdown
  function populateCannedSelect() {
    const select = shadowRoot.getElementById('chat-canned-select');
    select.innerHTML = '<option value="">Choose a template...</option>';
    
    cachedCannedResponses.forEach((response, index) => {
      const opt = document.createElement('option');
      opt.value = index;
      opt.textContent = response.title;
      select.appendChild(opt);
    });
    if (select.updateCustomDisplay) select.updateCustomDisplay();
  }

  // Fetch children of current Epic or detect if current issue is already a child (Service or Task)
  async function fetchAndPopulateChildren(parentKey) {
    const select = shadowRoot.getElementById('time-child-select');
    const createChildBtn = shadowRoot.getElementById('time-create-child');
    select.innerHTML = '<option value="">Fetching child issues...</option>';
    createChildBtn.classList.add('hide');

    const issueTypeObj = currentIssueData.fields.issuetype;
    const issueTypeName = issueTypeObj.name.toLowerCase();
    const hierarchyLevel = issueTypeObj.hierarchyLevel;
    
    // Determine if it is an Epic
    const isEpic = issueTypeName.includes('epic') || (typeof hierarchyLevel === 'number' && hierarchyLevel > 0);
    // Determine if it is a Sub-task
    const isSubtask = issueTypeObj.subtask || (typeof hierarchyLevel === 'number' && hierarchyLevel < 0);

    // If the current issue is already a standard level-1 issue (Task, Story, Services, etc.), we log directly on it
    if (!isEpic && !isSubtask) {
      select.innerHTML = `<option value="${parentKey}">Current issue (${parentKey})</option>`;
      select.value = parentKey;
      if (select.updateCustomDisplay) select.updateCustomDisplay();
      return;
    }

    // Otherwise, we search JIRA API for children under this Epic
    try {
      // Query 1: Try unified JQL parent search
      let jql = `parent = ${parentKey}`;
      let searchRes = await callJiraApi(`/rest/api/3/search/jql?jql=${encodeURIComponent(jql)}&fields=summary,issuetype`, 'GET');
      
      let rawIssues = [];
      if (searchRes.success && searchRes.data.issues) {
        rawIssues = searchRes.data.issues;
      }
      
      // Query 2: Fallback to Epic Link if first query returned nothing
      if (rawIssues.length === 0) {
        const jqlFallback = `"Epic Link" = ${parentKey}`;
        const searchResFallback = await callJiraApi(`/rest/api/3/search/jql?jql=${encodeURIComponent(jqlFallback)}&fields=summary,issuetype`, 'GET');
        if (searchResFallback.success && searchResFallback.data.issues) {
          rawIssues = searchResFallback.data.issues;
        }
      }

      // Filter locally in Javascript for robust matching (e.g. includes "service" or "task")
      const issues = rawIssues.filter(child => {
        if (!child.fields || !child.fields.issuetype) return false;
        const typeLower = child.fields.issuetype.name.toLowerCase();
        return typeLower.includes('service') || typeLower.includes('task');
      });

      if (issues.length === 0) {
        select.innerHTML = '<option value="">No Child Services/Tasks found!</option>';
        createChildBtn.classList.remove('hide');
      } else {
        select.innerHTML = '';
        issues.forEach(child => {
          const opt = document.createElement('option');
          opt.value = child.key;
          opt.textContent = `[${child.key}] ${child.fields.summary} (${child.fields.issuetype.name})`;
          select.appendChild(opt);
        });
        // Auto select if only one child
        if (issues.length === 1) {
          select.value = issues[0].key;
        } else {
          // insert a default prompt first
          const defaultOpt = document.createElement('option');
          defaultOpt.value = '';
          defaultOpt.textContent = `Choose one of ${issues.length} child issues...`;
          defaultOpt.disabled = true;
          select.insertBefore(defaultOpt, select.firstChild);
          select.value = '';
        }
      }
      if (select.updateCustomDisplay) select.updateCustomDisplay();
    } catch (e) {
      select.innerHTML = `<option value="">Fetch exception: ${e.message}</option>`;
      if (select.updateCustomDisplay) select.updateCustomDisplay();
      console.error(e);
    }
  }

  // Replaces canned responses placeholders dynamically
  function applyTemplatePlaceholders(templateText) {
    if (!currentIssueData) return templateText;
    
    const key = currentIssueData.key || '';
    const matchNum = key.match(/-(\d+)/);
    const keyNumber = matchNum ? matchNum[1] : '';

    const partnerName = formatJiraField(currentIssueData.fields.customfield_11180, '');
    const customerName = formatJiraField(currentIssueData.fields.customfield_11250, '');
    const productName = formatJiraField(currentIssueData.fields.customfield_11283, '');
    
    // Retrieve fix versions if any
    let fixVersion = '';
    if (currentIssueData.fields.fixVersions && currentIssueData.fields.fixVersions.length > 0) {
      fixVersion = currentIssueData.fields.fixVersions[0].name;
    } else {
      fixVersion = formatJiraField(currentIssueData.fields.customfield_11182, ''); // Fallback current version
    }

    let text = templateText;
    text = text.replace(/\[Όνομα Συνεργάτη\]/g, partnerName);
    text = text.replace(/\[Ονομα Συνεργάτη\]/g, partnerName); // handle potential spelling variations
    text = text.replace(/\[Όνομα Πελάτη\]/g, customerName);
    text = text.replace(/\[Ονομα Πελάτη\]/g, customerName);
    text = text.replace(/\[Product\]/g, productName);
    text = text.replace(/\[Έκδοση Fix\]/g, fixVersion);
    text = text.replace(/\[PYLCOM-XXXXXX\]/g, key);
    text = text.replace(/XXXXXX/g, keyNumber);
    
    // Get current user display name from Jira storage (saved on settings or fetched)
    const email = credentials ? credentials.email : '';
    const namePart = email.split('@')[0].split('.');
    const consultantName = namePart.map(n => n.charAt(0).toUpperCase() + n.slice(1)).join(' ');
    
    text = text.replace(/\[Ονομα Συμβούλου\]/g, consultantName);
    text = text.replace(/\[Ονοματεπώνυμο Συμβούλου\]/g, consultantName);

    return text;
  }

  // Network communications wrapper helper
  function callJiraApi(endpoint, method = 'GET', body = null) {
    return new Promise((resolve) => {
      if (!credentials) {
        resolve({ success: false, error: 'Credentials not configured' });
        return;
      }
      
      chrome.runtime.sendMessage(
        {
          action: 'JIRA_API_REQUEST',
          payload: { endpoint, method, body, credentials }
        },
        (response) => {
          if (chrome.runtime.lastError) {
            resolve({ success: false, error: chrome.runtime.lastError.message });
          } else {
            resolve(response);
          }
        }
      );
    });
  }

  // Helper to render UI messages
  function showStatus(element, message, type) {
    if (!element) return;
    element.textContent = message;
    element.className = 'pilot-status-msg ' + type;
    setTimeout(() => {
      // Clear after 8s on success/info, leave errors
      if (type !== 'error') {
        element.style.display = 'none';
      }
    }, 8000);
  }

  // Simple regex-based Markdown to HTML renderer for live preview in sidebar
  function renderMarkdownToHtml(markdown) {
    if (!markdown) return '<em>Nothing to preview</em>';
    
    // Escape HTML tags
    let html = markdown
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
      
    // 1. Bold: **text**
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // 2. Italic: _text_
    html = html.replace(/_(.*?)_/g, '<em>$1</em>');
    
    // 3. Links: [text](url)
    html = html.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank">$1</a>');
    
    // 4. Raw URLs auto-linking
    html = html.replace(/(?<!href=")(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank">$1</a>');
    
    // 5. Paragraphs & Lists
    const blocks = html.split(/\n\n+/);
    html = blocks.map(block => {
      const trimmed = block.trim();
      if (trimmed.startsWith('* ') || trimmed.startsWith('- ')) {
        const items = block.split(/\n[*+-]\s+/);
        items[0] = items[0].replace(/^[*+-]\s+/, '');
        return '<ul>' + items.map(li => `<li>${li.replace(/\n/g, '<br>')}</li>`).join('') + '</ul>';
      }
      if (trimmed.match(/^\d+\.\s+/)) {
        const items = block.split(/\n\d+\.\s+/);
        items[0] = items[0].replace(/^\d+\.\s+/, '');
        return '<ol>' + items.map(li => `<li>${li.replace(/\n/g, '<br>')}</li>`).join('') + '</ol>';
      }
      if (trimmed === '---') {
        return '<hr>';
      }
      return `<p>${block.replace(/\n/g, '<br>')}</p>`;
    }).join('');
    
    return html;
  }

  // Convert plain text with newlines into JIRA Atlassian Document Format (ADF)
  function convertTextToAdf(text) {
    if (!text) {
      return {
        type: 'doc',
        version: 1,
        content: []
      };
    }
    
    const lines = text.split('\n');
    const content = [];
    
    lines.forEach(line => {
      if (line.trim() === '') {
        content.push({
          type: 'paragraph',
          content: []
        });
      } else {
        content.push({
          type: 'paragraph',
          content: [
            {
              type: 'text',
              text: line
            }
          ]
        });
      }
    });
    
    return {
      type: 'doc',
      version: 1,
      content: content
    };
  }

  // Try inserting text into active contenteditable editor or textarea on JIRA page
  function insertTextIntoActiveJiraEditor(text) {
    const editors = document.querySelectorAll('[contenteditable="true"], textarea');
    let targetEditor = null;
    
    // 1. Try to find currently focused editor
    if (document.activeElement && 
        (document.activeElement.getAttribute('contenteditable') === 'true' || 
         document.activeElement.tagName === 'TEXTAREA')) {
      targetEditor = document.activeElement;
    }
    
    // 2. If not focused, search for any visible contenteditable editor
    if (!targetEditor && editors.length > 0) {
      for (let ed of editors) {
        const rect = ed.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          targetEditor = ed;
          break;
        }
      }
    }
    
    if (targetEditor) {
      targetEditor.focus();
      
      const htmlContent = renderMarkdownToHtml(text);
      
      if (targetEditor.tagName === 'TEXTAREA') {
        const start = targetEditor.selectionStart || 0;
        const end = targetEditor.selectionEnd || 0;
        const val = targetEditor.value;
        targetEditor.value = val.substring(0, start) + text + val.substring(end);
        return true;
      }
      
      // JIRA Rich Text Editor (contenteditable) - Try pasting HTML
      try {
        const sel = window.getSelection();
        if (!sel.rangeCount) {
          const range = document.createRange();
          range.selectNodeContents(targetEditor);
          range.collapse(false);
          sel.removeAllRanges();
          sel.addRange(range);
        }
        
        // Try Method A: Dispatch a synthetic paste event containing HTML data
        // ProseMirror intercepts this and parses the rich HTML natively!
        const dt = new DataTransfer();
        dt.setData('text/html', htmlContent);
        dt.setData('text/plain', text);
        const pasteEvent = new ClipboardEvent('paste', {
          bubbles: true,
          cancelable: true,
          clipboardData: dt
        });
        targetEditor.dispatchEvent(pasteEvent);
        return true;
      } catch (e1) {
        console.warn('Synthetic paste event failed, trying execCommand("insertHTML")...', e1);
        try {
          // Try Method B: execCommand('insertHTML')
          document.execCommand('insertHTML', false, htmlContent);
          return true;
        } catch (e2) {
          console.warn('execCommand("insertHTML") failed, trying execCommand("insertText")...', e2);
          try {
            // Try Method C: execCommand('insertText') (falls back to plain text)
            document.execCommand('insertText', false, text);
            return true;
          } catch (e3) {
            console.error('All rich insertion methods failed, falling back to innerHTML append:', e3);
            targetEditor.innerHTML = targetEditor.innerHTML + htmlContent;
            return true;
          }
        }
      }
    }
    return false;
  }
})();
