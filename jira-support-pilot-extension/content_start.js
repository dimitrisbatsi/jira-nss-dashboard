(function () {
  const captureEvents = ['mousedown', 'mouseup', 'click', 'pointerdown', 'pointerup', 'focusin', 'focusout'];
  
  captureEvents.forEach(evtName => {
    window.addEventListener(evtName, (e) => {
      const host = document.getElementById('support-pilot-shadow-host');
      if (!host) return;
      
      const path = e.composedPath();
      if (path.includes(host)) {
        // Stop the event from propagating to any other capture phase listeners on window/document (like Jira click-aways)
        e.stopPropagation();
        
        const target = path[0];
        if (target && target !== host) {
          // Determine the correct Event constructor
          let EventClass = MouseEvent;
          if (evtName.startsWith('pointer')) {
            EventClass = PointerEvent;
          } else if (evtName.startsWith('focus')) {
            EventClass = FocusEvent;
          }
          
          // Re-dispatch a clone of the event inside the Shadow DOM
          // composed: false prevents the cloned event from escaping the Shadow DOM boundary
          const newEvent = new EventClass(evtName, {
            bubbles: true,
            cancelable: true,
            composed: false,
            view: window,
            detail: e.detail,
            screenX: e.screenX,
            screenY: e.screenY,
            clientX: e.clientX,
            clientY: e.clientY,
            ctrlKey: e.ctrlKey,
            altKey: e.altKey,
            shiftKey: e.shiftKey,
            metaKey: e.metaKey,
            button: e.button,
            buttons: e.buttons,
            relatedTarget: e.relatedTarget
          });
          target.dispatchEvent(newEvent);
        }
      }
    }, true); // Register as capture-phase listener to execute BEFORE Jira listeners
  });
})();
