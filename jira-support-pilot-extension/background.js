// Listen for messages from content.js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'LOAD_CANNED_RESPONSES') {
    fetch(chrome.runtime.getURL('canned_responses.json'))
      .then(response => response.json())
      .then(data => sendResponse({ success: true, data }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true; // Keep message channel open for async response
  }

  if (message.action === 'JIRA_API_REQUEST') {
    const { endpoint, method, body, credentials } = message.payload;
    
    // Create base64 authorization header
    const authHeader = 'Basic ' + btoa(credentials.email + ':' + credentials.token);
    
    const url = `https://epsilon-singularlogic.atlassian.net${endpoint}`;
    
    const options = {
      method: method,
      headers: {
        'Authorization': authHeader,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-Atlassian-Token': 'no-check'
      }
    };
    
    if (body) {
      options.body = JSON.stringify(body);
    }
    
    fetch(url, options)
      .then(async response => {
        const text = await response.text();
        let data = {};
        try {
          data = text ? JSON.parse(text) : {};
        } catch (e) {
          data = { textResponse: text };
        }
        
        if (!response.ok) {
          let errMsg = 'API Request failed';
          if (data.errorMessages && Array.isArray(data.errorMessages) && data.errorMessages.length > 0) {
            errMsg = data.errorMessages.join(', ');
          } else if (data.errors && typeof data.errors === 'object' && Object.keys(data.errors).length > 0) {
            errMsg = Object.entries(data.errors).map(([k, v]) => `${k}: ${v}`).join('; ');
          } else if (data.message) {
            errMsg = data.message;
          } else if (data.textResponse) {
            errMsg = data.textResponse;
          }
          return {
            success: false,
            status: response.status,
            error: errMsg
          };
        }
        
        return {
          success: true,
          status: response.status,
          data: data
        };
      })
      .then(res => sendResponse(res))
      .catch(err => {
        console.error('Fetch error:', err);
        sendResponse({ success: false, error: err.message });
      });
      
    return true; // Keep message channel open for async response
  }
});
