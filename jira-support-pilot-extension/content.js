// Jira Support Pilot - Content Script
(function () {
  let shadowRoot = null;
  let currentIssueKey = '';
  let currentIssueData = null;
  let cachedCannedResponses = [];
  let credentials = null;
  let currentUserAccountId = null;
  let currentIsEpic = false;
  let currentEditingCustomIndex = -1;
  let editorMode = 'new'; // 'new' or 'edit'

  const TIME_TYPES_DATA = [
    {
      name: 'Support',
      desc: 'Διαχείριση αιτήματος, απάντηση, καθοδήγηση συνεργάτη — η κύρια δραστηριότητα',
      appliesTo: ['epic']
    },
    {
      name: 'Analysis',
      desc: 'Pre-implementation activity — όταν το αποτέλεσμα πάει σε enhancement ή πρόταση παραμετροποίησης από Support / Solution Design',
      appliesTo: ['epic', 'internal']
    },
    {
      name: 'Investigation',
      desc: 'Έρευνα αν ισχύει κάτι (bug), μελέτη παραμέτρων, αναπαραγωγή σεναρίου χωρίς επικοινωνία με συνεργάτη — manual, wiki, knowledge base, αναπαραγωγή',
      appliesTo: ['epic', 'internal']
    },
    {
      name: 'Test',
      desc: 'Ready to test / Έλεγχος νέας έκδοσης — αφορά ΜΟΝΟ ό,τι έρχεται από την παραγωγή για έλεγχο ορθότητας',
      appliesTo: ['epic', 'internal']
    },
    {
      name: 'Implementation',
      desc: 'Παραμετροποίηση, setup, configuration και υλοποίηση στο σύστημα του συνεργάτη — flex / direct',
      appliesTo: ['epic', 'internal']
    },
    {
      name: 'Phone Support',
      desc: 'Υποστήριξη μέσω τηλεφώνου / Αφορά υποδοχή αιτημάτων συνεργάτη μέσω τηλεφώνου.',
      appliesTo: ['epic']
    },
    {
      name: 'Training',
      desc: 'Εκπαίδευση συνεργάτη ή χρήστη βάσει συμφωνίας',
      appliesTo: ['epic']
    },
    {
      name: 'Documentation',
      desc: 'Καταγραφή οδηγιών / manual / Q&A',
      appliesTo: ['internal']
    },
    {
      name: 'Presales / Demo',
      desc: 'Παρουσιάσεις, demo σε πιθανό πελάτη — αφορά presales διαδικασία',
      appliesTo: ['epic', 'internal']
    },
    {
      name: 'Prototype',
      desc: 'Εργασίες στην πρότυπη βάση (prototype / sandbox environment)',
      appliesTo: ['internal']
    },
    {
      name: 'Complaint Handling',
      desc: 'Διαχείριση παραπόνου',
      appliesTo: ['epic']
    },
    {
      name: 'Internal Communication',
      desc: 'Επικοινωνία με συναδέλφους, ερώτηση σε 3rd level, εσωτερικός συντονισμός',
      appliesTo: ['epic', 'internal']
    },
    {
      name: 'Internal Meetings',
      desc: 'Team meetings, σχεδιασμός επόμενων βημάτων, planning, alignment ομάδας',
      appliesTo: ['epic', 'internal']
    },
    {
      name: 'Mentoring / Escalation (Giving)',
      desc: 'Καθοδήγηση που δίνει 3rd level ή senior σε ανοιχτό ticket άλλου consultant',
      appliesTo: ['epic']
    },
    {
      name: 'Mentoring / Escalation (Receiving)',
      desc: 'Χρόνος που αφιερώνει ο consultant για να λάβει καθοδήγηση / escalation πάνω στο δικό του ticket',
      appliesTo: ['epic']
    },
    {
      name: 'Trainer / Εκπαιδευτής',
      desc: 'Εσωτερικές εκπαιδεύσεις — ο consultant ως εισηγητής',
      appliesTo: ['internal']
    },
    {
      name: 'Trainee / Εκπαιδευόμενος',
      desc: 'Εσωτερικές εκπαιδεύσεις — ο consultant ως εκπαιδευόμενος',
      appliesTo: ['internal']
    },
    {
      name: 'Personal',
      desc: 'Προσωπικός χρόνος, διάλειμμα',
      appliesTo: ['internal']
    },
    {
      name: 'Routing',
      desc: 'Χρόνος που αναλώνεται για τον διαμοιρασμό των αιτημάτων',
      appliesTo: ['internal']
    },
    {
      name: 'Other',
      desc: 'Εάν δεν καλύπτεται καμία από τις παραπάνω',
      appliesTo: ['internal']
    },
    {
      name: 'Admin',
      desc: 'Διοικητικές / διαδικαστικές εργασίες',
      appliesTo: ['internal']
    }
  ];

  function populateTimeTypesSelect(projKey) {
    if (!shadowRoot) return;
    const select = shadowRoot.getElementById('time-type-select');
    const descDiv = shadowRoot.getElementById('time-type-description');
    if (!select) return;

    const isInternal = (projKey || '').toUpperCase() === 'PLINTS';
    const targetTag = isInternal ? 'internal' : 'epic';

    const filtered = TIME_TYPES_DATA.filter(t => t.appliesTo.includes(targetTag));

    select.innerHTML = '';
    filtered.forEach((t, idx) => {
      const opt = document.createElement('option');
      opt.value = t.name;
      opt.textContent = t.name;
      if (idx === 0) opt.selected = true;
      select.appendChild(opt);
    });

    const updateDescription = () => {
      const selectedVal = select.value;
      const found = TIME_TYPES_DATA.find(t => t.name === selectedVal);
      if (found && found.desc && descDiv) {
        descDiv.textContent = found.desc;
        descDiv.style.display = 'block';
      } else if (descDiv) {
        descDiv.style.display = 'none';
        descDiv.textContent = '';
      }
    };

    select.onchange = updateDescription;
    updateDescription();

    if (select.updateCustomDisplay) {
      select.updateCustomDisplay();
    }
  }

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
          let systemResponses = [];
          if (response && response.success) {
            systemResponses = response.data || [];
          } else {
            console.error('Error loading canned responses from background:', response ? response.error : 'No response');
          }
          
          // Load custom responses from local storage
          chrome.storage.local.get(['customCannedResponses'], (result) => {
            const customResponses = result.customCannedResponses || [];
            
            systemResponses.forEach(r => {
              if (!r.category) r.category = 'System';
            });
            
            customResponses.forEach(r => {
              r.category = 'Custom';
            });
            
            cachedCannedResponses = [...systemResponses, ...customResponses];
            populateCannedSelect();
            resolve(true);
          });
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

  // Retrieve NSS Support Hub Server URL from storage
  function getHubUrl() {
    return new Promise((resolve) => {
      chrome.storage.local.get(['pilotHubUrl'], (result) => {
        resolve(result.pilotHubUrl || 'http://dev-gemini:8501');
      });
    });
  }

  // Compare semver version strings
  function isNewerVersion(serverVer, currentVer) {
    if (!serverVer || !currentVer) return false;
    const sParts = serverVer.split('.').map(p => parseInt(p, 10) || 0);
    const cParts = currentVer.split('.').map(p => parseInt(p, 10) || 0);
    const maxLen = Math.max(sParts.length, cParts.length);
    for (let i = 0; i < maxLen; i++) {
      const s = sParts[i] || 0;
      const c = cParts[i] || 0;
      if (s > c) return true;
      if (s < c) return false;
    }
    return false;
  }

  // Check NSS Support Hub endpoint for extension updates
  async function checkExtensionUpdate() {
    const hubUrl = await getHubUrl();
    const manifestVer = chrome.runtime.getManifest().version;

    try {
      chrome.runtime.sendMessage({
        action: 'CHECK_EXTENSION_UPDATE',
        payload: { hubUrl }
      }, (response) => {
        if (chrome.runtime.lastError) {
          console.warn('Update check bypassed:', chrome.runtime.lastError.message);
          return;
        }
        if (response && response.success && response.data) {
          const serverVer = response.data.version;
          if (isNewerVersion(serverVer, manifestVer)) {
            const updateBanner = shadowRoot.getElementById('pilot-update-banner');
            const updateVersionText = shadowRoot.getElementById('pilot-update-version-text');
            const updateDownloadBtn = shadowRoot.getElementById('pilot-update-download-btn');
            
            if (updateBanner && updateVersionText && updateDownloadBtn) {
              updateVersionText.textContent = `v${serverVer} διαθέσιμη (Έχετε: v${manifestVer})`;
              const cleanBase = hubUrl.replace(/\/+$/, '');
              const downloadPath = response.data.download_url || '/app/static/jira-support-pilot-extension.zip';
              updateDownloadBtn.href = `${cleanBase}${downloadPath.startsWith('/') ? '' : '/'}${downloadPath}`;
              updateBanner.classList.remove('hide');
            }
          }
        }
      });
    } catch (err) {
      console.warn('Could not check extension update:', err);
    }
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
      
      Array.from(selectEl.children).forEach(child => {
        if (child.tagName.toUpperCase() === 'OPTGROUP') {
          // Add group header
          const groupHeader = document.createElement('div');
          groupHeader.className = 'pilot-custom-select-group-header';
          groupHeader.textContent = child.label;
          optionsContainer.appendChild(groupHeader);
          
          // Add group options
          Array.from(child.children).forEach(opt => {
            createOptionItem(opt, true);
          });
        } else if (child.tagName.toUpperCase() === 'OPTION') {
          createOptionItem(child, false);
        }
      });
      
      function createOptionItem(opt, isGrouped) {
        const item = document.createElement('div');
        item.className = 'pilot-custom-select-option';
        if (isGrouped) {
          item.classList.add('grouped');
        }
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
      }
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
    // Populate initial Time Types
    populateTimeTypesSelect('');

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
      const hubUrlInput = shadowRoot.getElementById('settings-hub-url');
      const hubUrl = (hubUrlInput ? hubUrlInput.value.trim() : '') || 'http://dev-gemini:8501';
      const statusDiv = shadowRoot.getElementById('settings-status');

      if (!email || !token) {
        showStatus(statusDiv, 'Please fill in both Email and Jira Token.', 'error');
        return;
      }

      chrome.storage.local.set({ jiraEmail: email, jiraToken: token, pilotHubUrl: hubUrl }, async () => {
        credentials = { email, token };
        showStatus(statusDiv, 'Settings saved successfully!', 'success');
        await fetchCurrentUser();
        refreshActiveIssue();
        checkExtensionUpdate();
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

    // Load credentials & Hub URL in inputs
    if (credentials) {
      shadowRoot.getElementById('settings-email').value = credentials.email;
      shadowRoot.getElementById('settings-token').value = credentials.token;
    }
    getHubUrl().then(url => {
      const hubUrlInput = shadowRoot.getElementById('settings-hub-url');
      if (hubUrlInput) hubUrlInput.value = url;
    });

    // Trigger update check on setup
    checkExtensionUpdate();


    // Chat Canned Selection Changed & Real-time Live Markdown Preview
    const cannedSelect = shadowRoot.getElementById('chat-canned-select');
    const previewArea = shadowRoot.getElementById('chat-text-preview');
    const markdownPreview = shadowRoot.getElementById('chat-markdown-preview');

    cannedSelect.addEventListener('change', () => {
      const selectedIndex = cannedSelect.value;
      const editBtn = shadowRoot.getElementById('canned-edit-btn');
      const deleteBtn = shadowRoot.getElementById('canned-delete-btn');
      
      if (selectedIndex === '' || !cachedCannedResponses[selectedIndex]) {
        previewArea.value = '';
        markdownPreview.innerHTML = '<em>Select a template or write a custom message to see preview...</em>';
        editBtn.classList.add('hide');
        deleteBtn.classList.add('hide');
        return;
      }
      
      const selectedResponse = cachedCannedResponses[selectedIndex];
      if (selectedResponse.category === 'Custom') {
        editBtn.classList.remove('hide');
        deleteBtn.classList.remove('hide');
      } else {
        editBtn.classList.add('hide');
        deleteBtn.classList.add('hide');
      }
      
      const rawTemplate = selectedResponse.body;
      const parsedText = applyTemplatePlaceholders(rawTemplate);
      previewArea.value = parsedText;
      markdownPreview.innerHTML = renderMarkdownToHtml(parsedText);
    });

    // Canned responses rebuild instructions toggle
    const rebuildBtn = shadowRoot.getElementById('canned-rebuild-btn');
    const rebuildInfo = shadowRoot.getElementById('canned-rebuild-info');
    if (rebuildBtn && rebuildInfo) {
      rebuildBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        rebuildInfo.classList.toggle('hide');
      });
    }

    // Canned responses Template Editor buttons
    const cannedNewBtn = shadowRoot.getElementById('canned-new-btn');
    const cannedEditBtn = shadowRoot.getElementById('canned-edit-btn');
    const cannedDeleteBtn = shadowRoot.getElementById('canned-delete-btn');
    const editorSaveBtn = shadowRoot.getElementById('editor-save-btn');
    const editorCancelBtn = shadowRoot.getElementById('editor-cancel-btn');
    const chatDefaultView = shadowRoot.getElementById('chat-default-view');
    const chatEditorView = shadowRoot.getElementById('chat-editor-view');
    const editorTitle = shadowRoot.getElementById('editor-view-title');
    const editorTitleInput = shadowRoot.getElementById('editor-template-title');
    const editorBodyInput = shadowRoot.getElementById('editor-template-body');

    // Create New Custom Template
    cannedNewBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      editorMode = 'new';
      currentEditingCustomIndex = -1;
      
      editorTitle.textContent = 'Create Custom Template';
      editorTitleInput.value = '';
      editorBodyInput.value = '';
      
      chatDefaultView.classList.add('hide');
      chatEditorView.classList.remove('hide');
    });

    // Edit Selected Custom Template
    cannedEditBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const selectedIndex = cannedSelect.value;
      if (selectedIndex === '' || !cachedCannedResponses[selectedIndex]) return;
      
      const selectedResponse = cachedCannedResponses[selectedIndex];
      if (selectedResponse.category !== 'Custom') return;

      editorMode = 'edit';
      editorTitle.textContent = 'Edit Custom Template';
      editorTitleInput.value = selectedResponse.title;
      editorBodyInput.value = selectedResponse.body;

      // Find index in customCannedResponses list to know which item to replace on Save
      chrome.storage.local.get(['customCannedResponses'], (result) => {
        const customList = result.customCannedResponses || [];
        currentEditingCustomIndex = customList.findIndex(r => r.title === selectedResponse.title);
        
        chatDefaultView.classList.add('hide');
        chatEditorView.classList.remove('hide');
      });
    });

    // Delete Selected Custom Template
    cannedDeleteBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const selectedIndex = cannedSelect.value;
      if (selectedIndex === '' || !cachedCannedResponses[selectedIndex]) return;
      
      const selectedResponse = cachedCannedResponses[selectedIndex];
      if (selectedResponse.category !== 'Custom') return;

      if (!confirm(`Are you sure you want to delete "${selectedResponse.title}"?`)) {
        return;
      }

      chrome.storage.local.get(['customCannedResponses'], (result) => {
        let customList = result.customCannedResponses || [];
        customList = customList.filter(r => r.title !== selectedResponse.title);
        
        chrome.storage.local.set({ customCannedResponses: customList }, async () => {
          cannedSelect.value = '';
          const event = new Event('change', { bubbles: true });
          cannedSelect.dispatchEvent(event);
          
          await loadCannedResponses();
        });
      });
    });

    // Cancel editing
    editorCancelBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      chatEditorView.classList.add('hide');
      chatDefaultView.classList.remove('hide');
    });

    // Save template (Insert or Update)
    editorSaveBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const title = editorTitleInput.value.trim();
      const body = editorBodyInput.value.trim();
      
      if (!title || !body) {
        alert('Please enter both Title and Template Content.');
        return;
      }

      chrome.storage.local.get(['customCannedResponses'], (result) => {
        const customList = result.customCannedResponses || [];
        
        if (editorMode === 'new') {
          // Check for duplicate title
          const titleExists = customList.some(r => r.title.toLowerCase() === title.toLowerCase());
          if (titleExists) {
            alert('A template with this title already exists. Please choose a unique title.');
            return;
          }
          customList.push({ title, body, category: 'Custom' });
        } else if (editorMode === 'edit') {
          if (currentEditingCustomIndex > -1 && currentEditingCustomIndex < customList.length) {
            // Check for duplicate title in other items
            const titleExists = customList.some((r, idx) => idx !== currentEditingCustomIndex && r.title.toLowerCase() === title.toLowerCase());
            if (titleExists) {
              alert('Another template with this title already exists. Please choose a unique title.');
              return;
            }
            customList[currentEditingCustomIndex] = { title, body, category: 'Custom' };
          } else {
            console.error('Invalid editing index:', currentEditingCustomIndex);
            return;
          }
        }

        chrome.storage.local.set({ customCannedResponses: customList }, async () => {
          chatEditorView.classList.add('hide');
          chatDefaultView.classList.remove('hide');
          
          await loadCannedResponses();
          
          // Try to select the saved template
          const newIndex = cachedCannedResponses.findIndex(r => r.title === title);
          if (newIndex > -1) {
            cannedSelect.value = newIndex;
            const event = new Event('change', { bubbles: true });
            cannedSelect.dispatchEvent(event);
          }
        });
      });
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

    // Normalize strings for project-agnostic mapping (handles dashes, spacing, etc.)
    function normalizeString(s) {
      if (!s) return '';
      return s.replace(/[^a-zA-Z0-9\u0370-\u03ff\u1f00-\u1fff]/g, '').toLowerCase();
    }

    // Fetch allowed values context for customfield_10553 dynamically
    async function fetchAllowedTimeTypes(projKey) {
      // Attempt 1: Call JIRA Cloud V3 /issue/createmeta endpoint
      try {
        const url = `/rest/api/3/issue/createmeta?projectKeys=${projKey}&issuetypeNames=Time Type&expand=projects.issuetypes.fields`;
        const res = await callJiraApi(url, 'GET');
        if (res.success && res.data && res.data.projects && res.data.projects.length > 0) {
          const proj = res.data.projects[0];
          if (proj.issuetypes && proj.issuetypes.length > 0) {
            const it = proj.issuetypes[0];
            if (it.fields && it.fields.customfield_10553) {
              const field = it.fields.customfield_10553;
              if (field.allowedValues) {
                return field.allowedValues; // Array of { id, value }
              }
            }
          }
        }
      } catch (e) {
        console.warn('Failed to fetch via createmeta query parameter version:', e);
      }
      
      // Attempt 2: Fallback to querying all issue types for the project to find the ID of "Time Type"
      try {
        const projMetaRes = await callJiraApi(`/rest/api/3/project/${projKey}`, 'GET');
        if (projMetaRes.success && projMetaRes.data) {
          const projectId = projMetaRes.data.id;
          const issueTypesRes = await callJiraApi(`/rest/api/3/issuetype`, 'GET');
          if (issueTypesRes.success && Array.isArray(issueTypesRes.data)) {
            const timeTypeObj = issueTypesRes.data.find(t => t.name.toLowerCase() === 'time type');
            if (timeTypeObj) {
              const issueTypeId = timeTypeObj.id;
              const contextUrl = `/rest/api/3/issue/createmeta/${projKey}/issuetypes/${issueTypeId}`;
              const metaRes = await callJiraApi(contextUrl, 'GET');
              if (metaRes.success && metaRes.data && metaRes.data.fields && metaRes.data.fields.customfield_10553) {
                const field = metaRes.data.fields.customfield_10553;
                if (field.allowedValues) {
                  return field.allowedValues;
                }
              }
            }
          }
        }
      } catch (e) {
        console.warn('Failed to fetch via project issue type path:', e);
      }

      return null;
    }

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

        // Fetch allowed values dynamically for this project context
        let customFieldVal = { value: selectedTimeType }; // Default fallback
        try {
          const allowedValues = await fetchAllowedTimeTypes(projKey);
          if (allowedValues && allowedValues.length > 0) {
            const normSelected = normalizeString(selectedTimeType);
            const matchedOption = allowedValues.find(opt => normalizeString(opt.value) === normSelected);
            if (matchedOption) {
              customFieldVal = { id: matchedOption.id };
            } else {
              // Try substring matching
              const partialMatch = allowedValues.find(opt => normalizeString(opt.value).includes(normSelected) || normSelected.includes(normalizeString(opt.value)));
              if (partialMatch) {
                customFieldVal = { id: partialMatch.id };
              }
            }
          }
        } catch (e) {
          console.warn('Failed to match time types dynamically:', e);
        }

        const createSubtaskPayload = {
          fields: {
            project: { key: projKey },
            parent: { key: selectedChildKey },
            summary: comment || 'Time Entry via Support Pilot',
            issuetype: { name: 'Time Type' }, // Set sub-task type to "Time Type"
            customfield_10553: customFieldVal, // Time Types (context-resolved ID or value fallback)
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

  function safeSetTextContent(id, text) {
    if (!shadowRoot) return;
    const el = shadowRoot.getElementById(id);
    if (el) {
      el.textContent = text;
    }
  }

  function resetUI() {
    safeSetTextContent('time-issue-key', currentIssueKey || 'No Active Issue');
    safeSetTextContent('time-issue-summary', '-');
    safeSetTextContent('time-issue-partner', '-');
    safeSetTextContent('time-issue-lsp', '-');
    safeSetTextContent('time-default-component', '-');
    
    safeSetTextContent('chat-issue-key', currentIssueKey || 'No Active Issue');
    safeSetTextContent('chat-issue-summary', '-');
    
    // Clear selections
    const childSelect = shadowRoot ? shadowRoot.getElementById('time-child-select') : null;
    if (childSelect) {
      childSelect.innerHTML = '<option value="">Choose child...</option>';
      if (childSelect.updateCustomDisplay) childSelect.updateCustomDisplay();
    }
    
    const timeCreateChild = shadowRoot ? shadowRoot.getElementById('time-create-child') : null;
    if (timeCreateChild) {
      timeCreateChild.classList.add('hide');
    }

    populateTimeTypesSelect('');
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
      const timeStatus = shadowRoot ? shadowRoot.getElementById('time-status') : null;
      if (timeStatus) showStatus(timeStatus, 'Credentials not configured. Go to Settings.', 'error');
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

        safeSetTextContent('time-issue-key', currentIssueKey);
        safeSetTextContent('time-issue-summary', summary);
        safeSetTextContent('time-issue-partner', partner);
        safeSetTextContent('time-issue-lsp', lsp);
        safeSetTextContent('time-default-component', component);

        safeSetTextContent('chat-issue-key', currentIssueKey);
        safeSetTextContent('chat-issue-summary', summary);

        // Detect if active ticket is Epic and update button labels
        const issueTypeObj = currentIssueData.fields.issuetype;
        const issueTypeName = issueTypeObj.name.toLowerCase();
        currentIsEpic = issueTypeName.includes('epic') || (typeof issueTypeObj.hierarchyLevel === 'number' && issueTypeObj.hierarchyLevel > 0);
        
        const chatSubmitBtn = shadowRoot ? shadowRoot.getElementById('chat-submit-btn') : null;
        if (chatSubmitBtn) {
          if (currentIsEpic) {
            chatSubmitBtn.textContent = '💬 Send Direct Comment (as yourself)';
          } else {
            chatSubmitBtn.textContent = '💬 Send Standard Comment (as yourself)';
          }
        }

        // Load Canned Select Options
        populateCannedSelect();

        // Populate Time Types dropdown based on space (PLINTS vs Epic spaces)
        const projKey = currentIssueKey.split('-')[0];
        populateTimeTypesSelect(projKey);

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
    
    const systemGroup = document.createElement('optgroup');
    systemGroup.label = 'System Templates';
    
    const customGroup = document.createElement('optgroup');
    customGroup.label = 'My Custom Templates';
    
    let hasSystem = false;
    let hasCustom = false;
    
    cachedCannedResponses.forEach((response, index) => {
      const opt = document.createElement('option');
      opt.value = index;
      opt.textContent = response.title;
      
      if (response.category === 'Custom') {
        customGroup.appendChild(opt);
        hasCustom = true;
      } else {
        systemGroup.appendChild(opt);
        hasSystem = true;
      }
    });
    
    if (hasSystem) select.appendChild(systemGroup);
    if (hasCustom) select.appendChild(customGroup);
    
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

  // Jira Priority & Partner Tier Row Colors
  function applyColors() {

    document.querySelectorAll('[role="row"]').forEach(row => {

      const text = row.innerText.toLowerCase();

      // reset
      row.style.removeProperty("background-color");

      // Partner Tier Gold
    if (text.includes("🟡")) {
      row.style.backgroundColor = "#F6E7A1";
      }

      // Highest / Blocker
    else if (text.includes("highest") || text.includes("blocker")) {
        row.style.backgroundColor = "#EFA3A3";
      }

      // Critical
    else if (text.includes("critical")) {
        row.style.backgroundColor = "#F5C2C2";
      }

      // High
    else if (text.includes("high")) {
        row.style.backgroundColor = "#F6D7C3";
      }

      // Medium / Major
    else if (text.includes("medium") || text.includes("major")) {
        row.style.backgroundColor = "#F8EED3";
      }

    else {
        row.style.backgroundColor = "";
      }

    });
  }


  // Jira is SPA, rows change dynamically
  const jiraColorObserver = new MutationObserver(() => {
    applyColors();
  });

  jiraColorObserver.observe(document.body, {
    childList: true,
    subtree: true
  });


  // Initial coloring
  applyColors();
})();
