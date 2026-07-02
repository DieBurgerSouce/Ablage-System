// Offline-Fallback-Logik fuer offline.html.
// Ausgelagert aus dem frueheren Inline-<script>, damit die Seite unter der
// gehaerteten CSP (script-src 'self', kein 'unsafe-inline') funktioniert.

function updateStatus() {
  var statusEl = document.getElementById('status');
  if (!statusEl) return;
  if (navigator.onLine) {
    statusEl.className = 'status online';
    statusEl.innerHTML = 'Verbindung wiederhergestellt - Seite wird neu geladen...';
    setTimeout(function () {
      window.location.reload();
    }, 1000);
  } else {
    statusEl.className = 'status';
    statusEl.innerHTML = '<span class="loading">Offline - Warte auf Verbindung...</span>';
  }
}

function tryReconnect() {
  var statusEl = document.getElementById('status');
  if (statusEl) {
    statusEl.innerHTML = '<span class="loading">Verbindung wird geprueft...</span>';
  }

  fetch('/', { method: 'HEAD', cache: 'no-store' })
    .then(function () {
      if (statusEl) {
        statusEl.className = 'status online';
        statusEl.innerHTML = 'Verbindung wiederhergestellt!';
      }
      setTimeout(function () {
        window.location.href = '/';
      }, 500);
    })
    .catch(function () {
      if (statusEl) {
        statusEl.className = 'status';
        statusEl.innerHTML = 'Noch keine Verbindung verfuegbar';
      }
    });
}

function goBack() {
  if (window.history.length > 1) {
    window.history.back();
  } else {
    window.location.href = '/';
  }
}

document.addEventListener('DOMContentLoaded', function () {
  var reconnectBtn = document.getElementById('reconnect-btn');
  var backBtn = document.getElementById('back-btn');
  if (reconnectBtn) reconnectBtn.addEventListener('click', tryReconnect);
  if (backBtn) backBtn.addEventListener('click', goBack);

  // Listen for online/offline events
  window.addEventListener('online', updateStatus);
  window.addEventListener('offline', updateStatus);

  // Initial check
  updateStatus();
});
