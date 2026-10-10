// Campus Quest - Client Map, Registration & Lobby Controller
// Mobile-first, zero local game state (all state verified against server cookies).

document.addEventListener('DOMContentLoaded', () => {
  const statusEl = document.getElementById('gps-status');

  // Modal elements
  const authOverlay = document.getElementById('auth-overlay');
  const lobbyOverlay = document.getElementById('lobby-overlay');
  const authAlert = document.getElementById('auth-alert');

  // Tab elements
  const tabBtnRegister = document.getElementById('tab-btn-register');
  const tabBtnJoin = document.getElementById('tab-btn-join');
  const formRegister = document.getElementById('form-register');
  const formJoin = document.getElementById('form-join');

  // Form inputs & controls
  const regTeamName = document.getElementById('reg-team-name');
  const membersContainer = document.getElementById('members-inputs');
  const btnAddMember = document.getElementById('btn-add-member');
  const btnSubmitRegister = document.getElementById('btn-submit-register');
  const joinTeamCode = document.getElementById('join-team-code');
  const btnSubmitJoin = document.getElementById('btn-submit-join');

  // Lobby elements
  const lobbyTeamName = document.getElementById('lobby-team-name');
  const lobbyTeamCode = document.getElementById('lobby-team-code');
  const lobbyMembersList = document.getElementById('lobby-members-list');
  const lobbyDeviceStatus = document.getElementById('lobby-device-status');
  const lobbyStatusBadge = document.getElementById('lobby-status-badge');
  const lobbyCountdownBanner = document.getElementById('lobby-countdown-banner');
  const lobbyCountdownSec = document.getElementById('lobby-countdown-sec');

  // Game screen placeholder elements
  const gameOverlay = document.getElementById('game-overlay');
  const gameScreenTeamName = document.getElementById('game-screen-team-name');
  const gameScreenBadge = document.getElementById('game-screen-badge');
  const gameScreenStatusDesc = document.getElementById('game-screen-status-desc');

  // Time & Polling State
  let serverOffsetMs = null;
  let countdownInterval = null;
  let pollingTimer = null;
  let pollIntervalMs = 4000;

  function setStatus(message, statusClass) {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.className = 'gps-status-pill ' + statusClass;
  }

  function showAlert(msg, isError = true) {
    if (!authAlert) return;
    authAlert.textContent = msg;
    authAlert.className = 'alert-box ' + (isError ? 'alert-error' : 'alert-success');
    authAlert.hidden = false;
  }

  function clearAlert() {
    if (!authAlert) return;
    authAlert.hidden = true;
    authAlert.textContent = '';
  }

  // --- Tab Navigation ---

  if (tabBtnRegister && tabBtnJoin) {
    tabBtnRegister.addEventListener('click', () => {
      tabBtnRegister.classList.add('active');
      tabBtnRegister.setAttribute('aria-selected', 'true');
      tabBtnJoin.classList.remove('active');
      tabBtnJoin.setAttribute('aria-selected', 'false');
      formRegister.hidden = false;
      formJoin.hidden = true;
      clearAlert();
    });

    tabBtnJoin.addEventListener('click', () => {
      tabBtnJoin.classList.add('active');
      tabBtnJoin.setAttribute('aria-selected', 'true');
      tabBtnRegister.classList.remove('active');
      tabBtnRegister.setAttribute('aria-selected', 'false');
      formJoin.hidden = false;
      formRegister.hidden = true;
      clearAlert();
    });
  }

  // --- Dynamic Member Inputs ---

  function updateMemberRows() {
    if (!membersContainer) return;
    const rows = membersContainer.querySelectorAll('.member-input-row');
    rows.forEach((row, index) => {
      const input = row.querySelector('.member-input');
      if (input && !input.value) {
        input.placeholder = index === 0 ? 'Member 1 (Captain)' : `Member ${index + 1}`;
      }
      let removeBtn = row.querySelector('.btn-remove-member');
      if (rows.length > 2) {
        if (!removeBtn) {
          removeBtn = document.createElement('button');
          removeBtn.type = 'button';
          removeBtn.className = 'btn-remove-member';
          removeBtn.setAttribute('aria-label', `Remove member ${index + 1}`);
          removeBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          `;
          removeBtn.addEventListener('click', () => {
            row.remove();
            updateMemberRows();
          });
          row.appendChild(removeBtn);
        }
      } else if (removeBtn) {
        removeBtn.remove();
      }
    });
  }

  if (btnAddMember && membersContainer) {
    btnAddMember.addEventListener('click', () => {
      const currentRows = membersContainer.querySelectorAll('.member-input-row');
      if (currentRows.length >= 8) {
        showAlert('Maximum 8 members permitted per team.');
        return;
      }
      const newIndex = currentRows.length + 1;
      const row = document.createElement('div');
      row.className = 'member-input-row';
      row.innerHTML = `
        <input type="text" class="member-input" required minlength="1" maxlength="30" placeholder="Member ${newIndex}" autocomplete="off">
      `;
      membersContainer.appendChild(row);
      updateMemberRows();
      const input = row.querySelector('.member-input');
      if (input) input.focus();
    });
    updateMemberRows();
  }

  // --- Registration Handler ---

  if (formRegister) {
    formRegister.addEventListener('submit', (e) => {
      e.preventDefault();
      clearAlert();

      const name = regTeamName ? regTeamName.value.trim() : '';
      if (name.length < 2 || name.length > 30) {
        showAlert('Team name must be between 2 and 30 characters.');
        return;
      }

      const memberInputs = membersContainer.querySelectorAll('.member-input');
      const members = [];
      memberInputs.forEach((input) => {
        const val = input.value.trim();
        if (val) members.push(val);
      });

      if (members.length < 2) {
        showAlert('Please provide at least 2 team members.');
        return;
      }

      btnSubmitRegister.disabled = true;
      btnSubmitRegister.textContent = 'Registering team...';

      fetch('/api/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, members }),
      })
        .then(async (res) => {
          btnSubmitRegister.disabled = false;
          btnSubmitRegister.textContent = 'Register team';
          const data = await res.json();
          if (!res.ok) {
            throw new Error(data.detail || 'Registration failed');
          }
          return data;
        })
        .then(() => {
          checkSession();
        })
        .catch((err) => {
          btnSubmitRegister.disabled = false;
          btnSubmitRegister.textContent = 'Register team';
          showAlert(err.message);
        });
    });
  }

  // --- Join Handler ---

  if (formJoin) {
    formJoin.addEventListener('submit', (e) => {
      e.preventDefault();
      clearAlert();

      const code = joinTeamCode ? joinTeamCode.value.trim().toUpperCase() : '';
      if (!code) {
        showAlert('Please enter a team code.');
        return;
      }

      btnSubmitJoin.disabled = true;
      btnSubmitJoin.textContent = 'Joining team...';

      fetch('/api/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })
        .then(async (res) => {
          btnSubmitJoin.disabled = false;
          btnSubmitJoin.textContent = 'Join with code';
          const data = await res.json();
          if (!res.ok) {
            throw new Error(data.detail || 'Failed to join team');
          }
          return data;
        })
        .then(() => {
          checkSession();
        })
        .catch((err) => {
          btnSubmitJoin.disabled = false;
          btnSubmitJoin.textContent = 'Join with code';
          showAlert(err.message);
        });
    });
  }

  // --- State, Lobby & Countdown Controller ---

  function updateGameState(state) {
    if (!state) return;

    // Compute clock offset once so client never trusts phone clock
    if (serverOffsetMs === null && typeof state.server_now_ms === 'number') {
      serverOffsetMs = state.server_now_ms - Date.now();
    }

    if (authOverlay) authOverlay.hidden = true;

    // Clear active countdown timer tick
    if (countdownInterval) {
      clearInterval(countdownInterval);
      countdownInterval = null;
    }

    const currentServerTime = Date.now() + (serverOffsetMs || 0);

    if (state.game_state === 'setup') {
      if (gameOverlay) gameOverlay.hidden = true;
      if (lobbyOverlay) lobbyOverlay.hidden = false;
      if (lobbyCountdownBanner) lobbyCountdownBanner.hidden = true;
      if (lobbyStatusBadge) {
        lobbyStatusBadge.textContent = 'Waiting for the organizer to start';
        lobbyStatusBadge.className = 'status-badge status-waiting';
      }
      populateLobbyDetails(state);
    } else if (state.game_state === 'running') {
      if (state.started_at_ms && currentServerTime < state.started_at_ms) {
        // Countdown is active
        if (gameOverlay) gameOverlay.hidden = true;
        if (lobbyOverlay) lobbyOverlay.hidden = false;
        if (lobbyCountdownBanner) lobbyCountdownBanner.hidden = false;
        if (lobbyStatusBadge) {
          lobbyStatusBadge.textContent = 'Quest starting shortly...';
          lobbyStatusBadge.className = 'status-badge status-waiting';
        }
        populateLobbyDetails(state);

        const updateCountdown = () => {
          const nowServer = Date.now() + (serverOffsetMs || 0);
          const remainingSec = Math.max(0, Math.ceil((state.started_at_ms - nowServer) / 1000));
          if (lobbyCountdownSec) lobbyCountdownSec.textContent = remainingSec;
          if (remainingSec <= 0) {
            clearInterval(countdownInterval);
            countdownInterval = null;
            showGamePlaceholder(state);
          }
        };
        updateCountdown();
        countdownInterval = setInterval(updateCountdown, 1000);
      } else {
        // Game has started and countdown has finished
        showGamePlaceholder(state);
      }
    } else if (state.game_state === 'ended') {
      if (lobbyOverlay) lobbyOverlay.hidden = true;
      if (gameOverlay) {
        gameOverlay.hidden = false;
        if (gameScreenTeamName) gameScreenTeamName.textContent = state.name || '---';
        if (gameScreenBadge) {
          gameScreenBadge.textContent = 'Quest Ended';
          gameScreenBadge.className = 'status-badge status-waiting';
        }
        if (gameScreenStatusDesc) {
          gameScreenStatusDesc.textContent = 'The event has concluded. View final leaderboard with organizers!';
        }
      }
    }
  }

  function showGamePlaceholder(state) {
    if (lobbyOverlay) lobbyOverlay.hidden = true;
    if (gameOverlay) {
      gameOverlay.hidden = false;
      if (gameScreenTeamName) gameScreenTeamName.textContent = state.name || '---';
      if (gameScreenBadge) {
        gameScreenBadge.textContent = 'Quest in progress';
        gameScreenBadge.className = 'status-badge placeholder-badge';
      }
      if (gameScreenStatusDesc) {
        gameScreenStatusDesc.textContent = 'Searching for Checkpoint #1...';
      }
    }
  }

  function populateLobbyDetails(state) {
    if (lobbyTeamName) lobbyTeamName.textContent = state.name;
    if (lobbyTeamCode) lobbyTeamCode.textContent = state.code;
    if (lobbyDeviceStatus && state.device_status) {
      lobbyDeviceStatus.textContent = state.device_status;
    }

    if (lobbyMembersList) {
      lobbyMembersList.innerHTML = '';
      (state.members || []).forEach((member) => {
        const li = document.createElement('li');
        li.className = 'member-chip';
        li.textContent = member;
        lobbyMembersList.appendChild(li);
      });
    }
  }

  // --- Session Restoration & Background Polling ---

  function startPolling() {
    if (pollingTimer) clearInterval(pollingTimer);
    pollingTimer = setInterval(() => {
      fetch('/api/state')
        .then((res) => {
          if (res.ok) return res.json();
          if (res.status === 401) {
            if (pollingTimer) {
              clearInterval(pollingTimer);
              pollingTimer = null;
            }
            if (authOverlay) authOverlay.hidden = false;
            if (lobbyOverlay) lobbyOverlay.hidden = true;
            if (gameOverlay) gameOverlay.hidden = true;
          }
          return null;
        })
        .then((state) => {
          if (state) updateGameState(state);
        })
        .catch(() => {});
    }, pollIntervalMs);
  }

  function checkSession() {
    fetch('/api/state')
      .then((res) => {
        if (res.ok) {
          return res.json().then((state) => {
            updateGameState(state);
            startPolling();
          });
        }
        if (res.status === 401) {
          if (authOverlay) authOverlay.hidden = false;
          if (lobbyOverlay) lobbyOverlay.hidden = true;
          if (gameOverlay) gameOverlay.hidden = true;
        }
      })
      .catch(() => {
        if (authOverlay) authOverlay.hidden = false;
        if (lobbyOverlay) lobbyOverlay.hidden = true;
        if (gameOverlay) gameOverlay.hidden = true;
      });
  }

  // Always check server session on page load
  checkSession();

  // --- Map & GPS Initialization ---

  fetch('/api/config')
    .then((response) => {
      if (!response.ok) {
        throw new Error('Server returned status ' + response.status);
      }
      return response.json();
    })
    .then((cfg) => {
      initMap(cfg);
    })
    .catch((err) => {
      setStatus('Failed to load map settings: ' + err.message, 'status-error');
    });

  function initMap(cfg) {
    const sw = L.latLng(cfg.bounds.sw.lat, cfg.bounds.sw.lng);
    const ne = L.latLng(cfg.bounds.ne.lat, cfg.bounds.ne.lng);
    const campusBounds = L.latLngBounds(sw, ne);

    const map = L.map('map', {
      center: [cfg.center.lat, cfg.center.lng],
      zoom: cfg.zoom.start,
      minZoom: cfg.zoom.min,
      maxZoom: cfg.zoom.max,
      maxBounds: campusBounds,
      maxBoundsViscosity: 1.0,
      zoomControl: false,
    });

    // Place zoom control at bottom-right so it does not collide with UI buttons
    L.control.zoom({ position: 'bottomright' }).addTo(map);

    L.tileLayer(cfg.tile_url, {
      attribution: cfg.tile_attribution,
      minZoom: cfg.zoom.min,
      maxZoom: cfg.zoom.max,
    }).addTo(map);

    if (!('geolocation' in navigator)) {
      setStatus('Geolocation is not supported by your browser.', 'status-error');
      return;
    }

    setStatus('Waiting for GPS...', 'status-waiting');

    let locationDot = null;
    let accuracyCircle = null;
    let initialFixApplied = false;

    function onLocationSuccess(position) {
      const lat = position.coords.latitude;
      const lng = position.coords.longitude;
      const accuracy = position.coords.accuracy;
      const latLng = [lat, lng];

      if (!locationDot) {
        accuracyCircle = L.circle(latLng, {
          radius: accuracy,
          color: '#1a73e8',
          weight: 1,
          opacity: 0.6,
          fillColor: '#1a73e8',
          fillOpacity: 0.12,
        }).addTo(map);

        locationDot = L.circleMarker(latLng, {
          radius: 8,
          fillColor: '#1a73e8',
          color: '#ffffff',
          weight: 3,
          opacity: 1,
          fillOpacity: 1,
        }).addTo(map);
      } else {
        locationDot.setLatLng(latLng);
        accuracyCircle.setLatLng(latLng);
        accuracyCircle.setRadius(accuracy);
      }

      if (!initialFixApplied) {
        if (campusBounds.contains(latLng)) {
          map.panTo(latLng);
        }
        initialFixApplied = true;
      }

      const accMetres = Math.round(accuracy);
      setStatus(`Accuracy: ${accMetres} m`, 'status-active');
    }

    function onLocationError(error) {
      let message = 'Unable to determine position.';
      switch (error.code) {
        case error.PERMISSION_DENIED:
          message = 'Location permission denied. Please allow access.';
          break;
        case error.POSITION_UNAVAILABLE:
          message = 'GPS position unavailable. Move outdoors.';
          break;
        case error.TIMEOUT:
          message = 'Waiting for GPS fix (timed out, retrying)...';
          break;
      }
      setStatus(message, 'status-error');
    }

    navigator.geolocation.watchPosition(
      onLocationSuccess,
      onLocationError,
      {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: 15000,
      }
    );
  }
});

