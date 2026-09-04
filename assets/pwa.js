(() => {
  let deferredPrompt = null;

  const isStandalone = () =>
    window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;

  const isIOS = () => /iphone|ipad|ipod/i.test(window.navigator.userAgent);

  const setStatus = () => {
    const node = document.getElementById('pwa-connectivity');
    if (!node) return;
    const online = navigator.onLine;
    node.textContent = online ? 'Online' : 'Offline · calculations paused';
    node.classList.toggle('is-offline', !online);
  };

  const setInstallVisibility = () => {
    const button = document.getElementById('pwa-install-button');
    if (!button) return;
    button.style.display = isStandalone() ? 'none' : '';
  };

  const showHelp = () => {
    const help = document.getElementById('pwa-install-help');
    if (!help) return;
    const text = document.getElementById('pwa-install-help-text');
    if (text) {
      text.textContent = isIOS()
        ? 'On iPhone/iPad: tap Share in Safari, then choose Add to Home Screen.'
        : 'Use your browser menu and choose Install app or Add to Home screen.';
    }
    help.style.display = 'flex';
  };
  const bindControls = () => {
    const install = document.getElementById('pwa-install-button');
    if (install && !install.dataset.pwaBound) {
      install.dataset.pwaBound = '1';
      install.addEventListener('click', async () => {
        if (deferredPrompt) {
          deferredPrompt.prompt();
          await deferredPrompt.userChoice;
          deferredPrompt = null;
          setInstallVisibility();
        } else {
          showHelp();
        }
      });
    }
    const close = document.getElementById('pwa-install-close');
    if (close && !close.dataset.pwaBound) {
      close.dataset.pwaBound = '1';
      close.addEventListener('click', () => {
        const help = document.getElementById('pwa-install-help');
        if (help) help.style.display = 'none';
      });
    }
    setStatus();
    setInstallVisibility();
  };

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/service-worker.js', {scope: '/'}).catch(console.error);
    });
  }

  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    deferredPrompt = event;
    bindControls();
  });
  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    bindControls();
  });
  window.addEventListener('online', setStatus);
  window.addEventListener('offline', setStatus);

  const observer = new MutationObserver(() => {
    if (document.getElementById('pwa-install-button') && document.getElementById('pwa-install-close')) {
      observer.disconnect();
      bindControls();
    }
  });
  const boot = () => {
    bindControls();
    if (!document.getElementById('pwa-install-button')) {
      observer.observe(document.documentElement, {childList: true, subtree: true});
    }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
