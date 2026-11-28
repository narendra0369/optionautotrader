// OptionX V7 PWA install support: NO broker logic or account/token storage.
const installButton = document.getElementById('installOptionX');
const status = document.getElementById('mobileInstallStatus');
let deferredInstall = null;

const installed = () =>
  (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) ||
  window.navigator.standalone === true;

if (installButton) {
  installButton.hidden = true;
  installButton.disabled = true;

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    if (installed()) return;
    deferredInstall = event;
    installButton.hidden = false;
    installButton.disabled = false;
    if (status) status.textContent = 'Install OptionX from your browser. Broker orders stay OFF.';
  });
  window.addEventListener('appinstalled', () => {
    deferredInstall = null;
    installButton.hidden = true;
    installButton.disabled = true;
    if (status) status.textContent = 'OptionX app installed. Real trades remain disabled.';
  });
  installButton.addEventListener('click', async () => {
    if (!deferredInstall) {
      if (status) status.textContent = 'Chrome menu → Add to Home screen / Install app.';
      return;
    }
    const prompt = deferredInstall;
    deferredInstall = null;
    installButton.disabled = true;
    try {
      await prompt.prompt();
      const choice = await prompt.userChoice;
      if (choice?.outcome !== 'accepted') {
        installButton.disabled = false;
        installButton.hidden = true;
        if (status) status.textContent = 'Chrome menu → Add to Home screen.';
      }
    } catch {
      if (status) status.textContent = 'Browser installation unavailable. Use Chrome menu → Add to Home screen.';
      installButton.hidden = true;
    }
  });
}

if ('serviceWorker' in navigator && /^https:$/.test(location.protocol)) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', {scope:'/'})
      .catch(() => {
        if (status) status.textContent = 'App offline screen unavailable. Use Chrome for full access.';
      });
  });
}

// IMPORTANT: Do not cache authenticated Supabase, brokerage, candle or
// order-readiness requests. Offline means OFFLINE, never paper auto running.
