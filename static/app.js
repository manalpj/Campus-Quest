// Campus Quest - Client Map, Registration, Lobby & Game Screen Controller
// Mobile-first, zero local game state (all state verified against server cookies).

document.addEventListener('DOMContentLoaded', () => {
  // Navigation & Status elements
  const statusBar = document.getElementById('game-status-bar');
  const btnNav = document.getElementById('btn-nav');
  const statusClearedEl = document.getElementById('status-cleared');
  const statusTimerEl = document.getElementById('status-timer');
  const statusGpsEl = document.getElementById('gps-status') || document.getElementById('status-gps');
  const statusReconnectingEl = document.getElementById('status-reconnecting');

  // Reliability & Operational Notice elements
  const inappBrowserBanner = document.getElementById('inapp-browser-banner');
  const btnDismissInapp = document.getElementById('btn-dismiss-inapp');
  const wakelockNotice = document.getElementById('wakelock-notice');
  const btnDismissWakelock = document.getElementById('btn-dismiss-wakelock');
  const gpsPermissionGuide = document.getElementById('gps-permission-guide');
  const btnRetryGps = document.getElementById('btn-retry-gps');

  // Clue Card elements
  const clueCard = document.getElementById('game-clue-card');
  const clueTargetLabel = document.getElementById('clue-target-label');
  const clueTextEl = document.getElementById('clue-text');

  // Tab Navigation elements
  const gameTabBar = document.getElementById('game-tab-bar');
  const tabGameMap = document.getElementById('tab-game-map');
  const tabGameLeaderboard = document.getElementById('tab-game-leaderboard');
  const tabGameTeam = document.getElementById('tab-game-team');
  const btnLeaderboard = document.getElementById('btn-leaderboard');

  // Team View Panel elements
  const viewTeam = document.getElementById('view-team');
  const teamInfoName = document.getElementById('team-info-name');
  const teamInfoCode = document.getElementById('team-info-code');
  const teamInfoDevice = document.getElementById('team-info-device');
  const teamInfoMembers = document.getElementById('team-info-members');
  const btnCloseTeam = document.getElementById('btn-close-team');

  // Leaderboard View Panel elements
  const viewLeaderboard = document.getElementById('view-leaderboard');
  const leaderboardTbody = document.getElementById('leaderboard-tbody');
  const btnCloseLeaderboard = document.getElementById('btn-close-leaderboard');

  // Rules & FAQ View Panel elements
  const tabGameRules = document.getElementById('tab-game-rules');
  const viewRules = document.getElementById('view-rules');
  const rulesListContainer = document.getElementById('rules-list-container');
  const faqListContainer = document.getElementById('faq-list-container');
  const btnCloseRules = document.getElementById('btn-close-rules');
  const btnLobbyOpenRules = document.getElementById('btn-lobby-open-rules');
  const testModeBanner = document.getElementById('test-mode-banner');

  // Finish Screen elements
  const finishOverlay = document.getElementById('finish-overlay');
  const finishFinalRank = document.getElementById('finish-final-rank');
  const finishFinalTime = document.getElementById('finish-final-time');

  // Route & History Overlay elements
  const navOverlay = document.getElementById('nav-overlay');
  const btnCloseNav = document.getElementById('btn-close-nav');
  const historyItemsContainer = document.getElementById('history-items-container');

  // Unlock Modal elements
  const unlockOverlay = document.getElementById('unlock-overlay');
  const unlockCpName = document.getElementById('unlock-cp-name');
  const unlockStoryBox = document.getElementById('unlock-story-box');
  const unlockStoryText = document.getElementById('unlock-story-text');
  const btnUnlockContinue = document.getElementById('btn-unlock-continue');

  // Auth & Lobby modal elements
  const authOverlay = document.getElementById('auth-overlay');
  const lobbyOverlay = document.getElementById('lobby-overlay');
  const authAlert = document.getElementById('auth-alert');

  // Registration & Join forms
  const tabBtnRegister = document.getElementById('tab-btn-register');
  const tabBtnJoin = document.getElementById('tab-btn-join');
  const formRegister = document.getElementById('form-register');
  const formJoin = document.getElementById('form-join');
  const regTeamName = document.getElementById('reg-team-name');
  const membersContainer = document.getElementById('members-inputs');
  const btnAddMember = document.getElementById('btn-add-member');
  const btnSubmitRegister = document.getElementById('btn-submit-register');
  const joinTeamCode = document.getElementById('join-team-code');
  const btnSubmitJoin = document.getElementById('btn-submit-join');

  // Lobby details
  const lobbyTeamName = document.getElementById('lobby-team-name');
  const lobbyTeamCode = document.getElementById('lobby-team-code');
  const lobbyMembersList = document.getElementById('lobby-members-list');
  const lobbyDeviceStatus = document.getElementById('lobby-device-status');
  const lobbyStatusBadge = document.getElementById('lobby-status-badge');
  const lobbyCountdownBanner = document.getElementById('lobby-countdown-banner');
  const lobbyCountdownSec = document.getElementById('lobby-countdown-sec');

  // Power-up Tray, HUD, & Hint Modal elements
  const powerupTray = document.getElementById('powerup-tray');
  const btnPowerupHint = document.getElementById('btn-powerup-hint');
  const powerupHintBadge = document.getElementById('powerup-hint-badge');
  const btnPowerupRadar = document.getElementById('btn-powerup-radar');
  const powerupRadarBadge = document.getElementById('powerup-radar-badge');
  const btnPowerupBoost = document.getElementById('btn-powerup-boost');
  const powerupBoostBadge = document.getElementById('powerup-boost-badge');

  const hudRadarBadge = document.getElementById('hud-radar-badge');
  const hudRadarText = document.getElementById('hud-radar-text');
  const hudBoostBadge = document.getElementById('hud-boost-badge');
  const hudBoostSec = document.getElementById('hud-boost-sec');

  const clueHintBox = document.getElementById('clue-hint-box');
  const clueHintText = document.getElementById('clue-hint-text');

  const hintConfirmOverlay = document.getElementById('hint-confirm-overlay');
  const btnHintCancel = document.getElementById('btn-hint-cancel');
  const btnHintConfirm = document.getElementById('btn-hint-confirm');
  const powerupToast = document.getElementById('powerup-toast');

  const btnSkipClue = document.getElementById('btn-skip-clue');
  const skipConfirmOverlay = document.getElementById('skip-confirm-overlay');
  const btnSkipCancel = document.getElementById('btn-skip-cancel');
  const btnSkipConfirm = document.getElementById('btn-skip-confirm');

  // Application & Map State
  let serverOffsetMs = null;
  let countdownInterval = null;
  let pollingTimer = null;
  let pingTimer = null;
  let elapsedTimer = null;
  let pollIntervalMs = 4000;
  let pingIntervalMs = 4000;
  let currentGameState = null;

  let latestFix = null;
  let lastSentFixTs = 0;
  let mapInstance = null;
  let campusBounds = null;
  let locationDot = null;
  let accuracyCircle = null;
  let initialFixApplied = false;
  const clearedMarkersMap = new Map(); // id -> L.marker

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function setGpsStatus(message, statusClass) {
    if (!statusGpsEl) return;
    statusGpsEl.textContent = message;
    statusGpsEl.className = 'chip chip-gps ' + statusClass;
  }

  function showReconnecting(message) {
    if (statusReconnectingEl) {
      const textEl = statusReconnectingEl.querySelector('.banner-text');
      if (textEl && message) {
        textEl.textContent = message;
      }
      statusReconnectingEl.hidden = false;
    }
  }

  function hideReconnecting() {
    if (statusReconnectingEl) statusReconnectingEl.hidden = true;
  }

  // --- Network Online / Offline Detection ---
  window.addEventListener('offline', () => {
    showReconnecting('You are offline. Reconnecting automatically when signal returns...');
  });

  window.addEventListener('online', () => {
    hideReconnecting();
    fetchState();
    if (viewLeaderboard && !viewLeaderboard.hidden) {
      fetchLeaderboard();
    }
  });

  // --- In-App Browser Detection (Advisory Hint) ---
  function detectInAppBrowser() {
    const ua = navigator.userAgent || '';
    return /FBAN|FBAV|Instagram|Line\/|MicroMessenger|Snapchat|BytedanceWebview|Musical_ly|Twitter|FBIOS|GSA/i.test(ua);
  }

  if (inappBrowserBanner && detectInAppBrowser()) {
    inappBrowserBanner.hidden = false;
  }

  if (btnDismissInapp && inappBrowserBanner) {
    btnDismissInapp.addEventListener('click', () => {
      inappBrowserBanner.hidden = true;
    });
  }

  // --- Screen Wake Lock API Management ---
  let wakeLockSentinel = null;
  let wakeLockDismissed = false;

  if (btnDismissWakelock && wakelockNotice) {
    btnDismissWakelock.addEventListener('click', () => {
      wakeLockDismissed = true;
      wakelockNotice.hidden = true;
    });
  }

  async function requestWakeLock() {
    if (!currentGameState || currentGameState.game_state !== 'running' || currentGameState.finished) {
      releaseWakeLock();
      return;
    }

    if (document.visibilityState !== 'visible') {
      return;
    }

    if ('wakeLock' in navigator) {
      try {
        wakeLockSentinel = await navigator.wakeLock.request('screen');
        if (wakelockNotice) wakelockNotice.hidden = true;

        wakeLockSentinel.addEventListener('release', () => {
          wakeLockSentinel = null;
          // Re-show fallback notice if game is still active, page visible, and not dismissed
          if (currentGameState && currentGameState.game_state === 'running' && !currentGameState.finished) {
            if (document.visibilityState === 'visible' && !wakeLockDismissed && wakelockNotice) {
              wakelockNotice.hidden = false;
            }
          }
        });
      } catch (err) {
        // Unsupported on OS level, low battery, or permission denied
        wakeLockSentinel = null;
        if (!wakeLockDismissed && wakelockNotice) {
          wakelockNotice.hidden = false;
        }
      }
    } else {
      // Wake Lock API completely unsupported in browser
      wakeLockSentinel = null;
      if (!wakeLockDismissed && wakelockNotice) {
        wakelockNotice.hidden = false;
      }
    }
  }

  function releaseWakeLock() {
    if (wakeLockSentinel) {
      try {
        wakeLockSentinel.release();
      } catch (e) {}
      wakeLockSentinel = null;
    }
    if (wakelockNotice) {
      wakelockNotice.hidden = true;
    }
  }

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      requestWakeLock();
    }
  });

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

  // --- Auth Tabs & Dynamic Member Inputs ---

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

  // --- Registration & Join Submit ---

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

  // --- Bottom Tabs & Overlay Navigation ---

  let isTestModeActive = false;
  let cachedRules = null;

  function setTestMode(active) {
    isTestModeActive = active;
    if (testModeBanner) {
      testModeBanner.hidden = !active;
    }
    const mapEl = document.getElementById('map');
    if (mapEl) {
      mapEl.classList.toggle('test-mode-map', active);
    }
    document.body.classList.toggle('test-mode-active', active);
  }

  function fetchRules(force = false) {
    if (cachedRules && !force) {
      renderRules(cachedRules);
      return;
    }
    fetch('/api/rules')
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load rules');
        return res.json();
      })
      .then((data) => {
        cachedRules = data;
        renderRules(data);
      })
      .catch((err) => {
        if (rulesListContainer) {
          rulesListContainer.innerHTML = `<p class="field-hint error-hint">${escapeHtml(err.message)}</p>`;
        }
      });
  }

  function renderRules(data) {
    if (rulesListContainer && Array.isArray(data.rules)) {
      rulesListContainer.innerHTML = data.rules.map((r) => `
        <article class="rule-card">
          <h4 class="rule-card-title">${escapeHtml(r.title)}</h4>
          <p class="rule-card-text">${escapeHtml(r.text)}</p>
        </article>
      `).join('');
    }
    if (faqListContainer && Array.isArray(data.faq)) {
      faqListContainer.innerHTML = data.faq.map((item) => `
        <details class="faq-item">
          <summary class="faq-question">
            <span>${escapeHtml(item.q)}</span>
          </summary>
          <div class="faq-answer">
            <p>${escapeHtml(item.a)}</p>
          </div>
        </details>
      `).join('');
    }
  }

  function updatePlayerLocation(lat, lng, accuracy) {
    if (!mapInstance) return;
    const latLng = [lat, lng];
    const acc = typeof accuracy === 'number' ? accuracy : 5.0;

    latestFix = {
      lat,
      lng,
      accuracy: acc,
      ts: Date.now() / 1000,
    };

    if (!locationDot) {
      accuracyCircle = L.circle(latLng, {
        radius: acc,
        color: '#1a73e8',
        weight: 1,
        opacity: 0.6,
        fillColor: '#1a73e8',
        fillOpacity: 0.12,
      }).addTo(mapInstance);

      locationDot = L.circleMarker(latLng, {
        radius: 8,
        fillColor: '#1a73e8',
        color: '#ffffff',
        weight: 3,
        opacity: 1,
        fillOpacity: 1,
      }).addTo(mapInstance);
    } else {
      locationDot.setLatLng(latLng);
      if (accuracyCircle) {
        accuracyCircle.setLatLng(latLng);
        accuracyCircle.setRadius(acc);
      }
    }
  }

  function sendSimulatedPing(lat, lng) {
    if (!currentGameState || currentGameState.game_state !== 'running' || currentGameState.finished) {
      showPowerupToast('Cannot fake location: Start the game in /gods first');
      return;
    }
    const testFix = {
      lat: Number(lat.toFixed(6)),
      lng: Number(lng.toFixed(6)),
      accuracy: 5.0,
      ts: Date.now() / 1000,
      test: true,
    };

    updatePlayerLocation(testFix.lat, testFix.lng, testFix.accuracy);
    showPowerupToast(`📍 Simulated location (${testFix.lat.toFixed(4)}, ${testFix.lng.toFixed(4)})`);

    fetch('/api/ping', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(testFix),
    })
      .then(async (res) => {
        hideReconnecting();
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          if (res.status === 403) {
            showPowerupToast('⚠️ Test mode refused by server (403)');
            setTestMode(false);
          } else {
            showPowerupToast(`Ping error: ${data.detail || res.status}`);
          }
          return null;
        }
        return data;
      })
      .then((data) => {
        if (!data) return;
        if (data.status === 'unlocked') {
          showUnlockModal(data.checkpoint_name || 'Checkpoint', data.story, data.next_clue);
          if (data.awarded_powerup) {
            const label = data.awarded_powerup === 'radar' ? 'Radar' : 'Radius Boost';
            showPowerupToast(`🎉 Awarded 1 ${label}!`);
          }
          fetchState();
        } else if (data.status === 'searching') {
          showPowerupToast('Simulated fix processed');
          setGpsStatus('Simulated GPS fix sent', 'chip-good');
        } else if (data.status === 'completed') {
          fetchState();
          showFinishScreen();
        }
      })
      .catch((err) => {
        showPowerupToast(`Network error: ${err.message}`);
      });
  }

  function switchTab(target) {
    if (tabGameMap) {
      tabGameMap.classList.toggle('active', target === 'map');
      tabGameMap.setAttribute('aria-selected', target === 'map' ? 'true' : 'false');
    }
    if (tabGameLeaderboard) {
      tabGameLeaderboard.classList.toggle('active', target === 'leaderboard');
      tabGameLeaderboard.setAttribute('aria-selected', target === 'leaderboard' ? 'true' : 'false');
    }
    if (tabGameTeam) {
      tabGameTeam.classList.toggle('active', target === 'team');
      tabGameTeam.setAttribute('aria-selected', target === 'team' ? 'true' : 'false');
    }
    if (tabGameRules) {
      tabGameRules.classList.toggle('active', target === 'rules');
      tabGameRules.setAttribute('aria-selected', target === 'rules' ? 'true' : 'false');
    }

    if (viewTeam) viewTeam.hidden = (target !== 'team');
    if (viewRules) {
      viewRules.hidden = (target !== 'rules');
      if (target === 'rules') {
        fetchRules();
      }
    }
    if (viewLeaderboard) {
      viewLeaderboard.hidden = (target !== 'leaderboard');
      if (target === 'leaderboard') {
        fetchLeaderboard();
      }
    }
    if (target === 'map' && mapInstance) {
      setTimeout(() => {
        mapInstance.invalidateSize();
      }, 50);
    }
  }

  if (tabGameMap) {
    tabGameMap.addEventListener('click', () => switchTab('map'));
  }

  if (tabGameLeaderboard) {
    tabGameLeaderboard.addEventListener('click', () => switchTab('leaderboard'));
  }

  if (tabGameTeam) {
    tabGameTeam.addEventListener('click', () => switchTab('team'));
  }

  if (tabGameRules) {
    tabGameRules.addEventListener('click', () => switchTab('rules'));
  }

  if (btnLeaderboard) {
    btnLeaderboard.addEventListener('click', () => switchTab('leaderboard'));
  }

  if (btnCloseLeaderboard) {
    btnCloseLeaderboard.addEventListener('click', () => switchTab('map'));
  }

  if (btnCloseTeam) {
    btnCloseTeam.addEventListener('click', () => switchTab('map'));
  }

  if (btnCloseRules) {
    btnCloseRules.addEventListener('click', () => switchTab('map'));
  }

  if (btnLobbyOpenRules) {
    btnLobbyOpenRules.addEventListener('click', () => switchTab('rules'));
  }

  if (btnNav && navOverlay) {
    btnNav.addEventListener('click', () => {
      navOverlay.hidden = false;
    });
  }

  if (btnCloseNav && navOverlay) {
    btnCloseNav.addEventListener('click', () => {
      navOverlay.hidden = true;
    });
  }

  if (btnUnlockContinue && unlockOverlay) {
    btnUnlockContinue.addEventListener('click', () => {
      unlockOverlay.hidden = true;
    });
  }

  // --- Leaderboard Controller ---

  function fetchLeaderboard() {
    return fetch('/api/leaderboard')
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load leaderboard');
        return res.json();
      })
      .then((data) => {
        renderLeaderboard(data);
        return data;
      })
      .catch(() => {
        if (leaderboardTbody && (!leaderboardTbody.children.length || leaderboardTbody.querySelector('.leaderboard-empty-row'))) {
          leaderboardTbody.innerHTML = `
            <tr>
              <td colspan="4" class="leaderboard-empty-row">Unable to load rankings. Retrying...</td>
            </tr>
          `;
        }
        return null;
      });
  }

  function renderLeaderboard(data) {
    if (!leaderboardTbody) return;
    if (!data || data.length === 0) {
      leaderboardTbody.innerHTML = `
        <tr>
          <td colspan="4" class="leaderboard-empty-row">No teams registered yet.</td>
        </tr>
      `;
      return;
    }

    const currentCode = currentGameState ? currentGameState.code : null;
    const currentName = currentGameState ? currentGameState.name : null;

    let html = '';
    data.forEach((t) => {
      const isSelf = (currentCode && t.code === currentCode) || (currentName && t.name === currentName);
      const rowClass = isSelf ? ' class="leaderboard-row-self"' : '';
      const badgeClass = t.rank <= 3 ? ` rank-badge-${t.rank}` : '';
      const selfTag = isSelf ? '<span class="leaderboard-self-tag">You</span>' : '';

      html += `
        <tr${rowClass}>
          <td class="td-rank">
            <span class="rank-badge${badgeClass}">${t.rank}</span>
          </td>
          <td>
            <div class="leaderboard-team-name-cell">
              <span>${escapeHtml(t.name)}</span>
              ${selfTag}
            </div>
          </td>
          <td class="td-cleared">${t.cleared}/${t.total}</td>
          <td class="td-time">${escapeHtml(t.adjusted_time)}</td>
        </tr>
      `;
    });

    leaderboardTbody.innerHTML = html;
  }

  // --- State, Lobby & Active Game Controller ---

  function updateGameState(state) {
    if (!state) return;
    currentGameState = state;
    hideReconnecting();
    setTestMode(Boolean(state.test_mode));

    // Compute clock offset once so client relies strictly on server time
    if (serverOffsetMs === null && typeof state.server_now_ms === 'number') {
      serverOffsetMs = state.server_now_ms - Date.now();
    }

    if (authOverlay) authOverlay.hidden = true;

    // Clear active countdown interval if changing state
    if (countdownInterval) {
      clearInterval(countdownInterval);
      countdownInterval = null;
    }

    const currentServerTime = Date.now() + (serverOffsetMs || 0);

    if (state.game_state === 'setup') {
      releaseWakeLock();
      if (statusBar) statusBar.hidden = true;
      if (clueCard) clueCard.hidden = true;
      if (gameTabBar) gameTabBar.hidden = true;
      if (viewTeam) viewTeam.hidden = true;
      if (lobbyOverlay) lobbyOverlay.hidden = false;
      if (lobbyCountdownBanner) lobbyCountdownBanner.hidden = true;
      if (lobbyStatusBadge) {
        lobbyStatusBadge.textContent = 'Waiting for the organizer to start';
        lobbyStatusBadge.className = 'status-badge status-waiting';
      }
      populateLobbyDetails(state);
      stopElapsedTimer();
    } else if (state.game_state === 'running') {
      if (state.started_at_ms && currentServerTime < state.started_at_ms) {
        // Countdown active
        releaseWakeLock();
        if (statusBar) statusBar.hidden = true;
        if (clueCard) clueCard.hidden = true;
        if (gameTabBar) gameTabBar.hidden = true;
        if (viewTeam) viewTeam.hidden = true;
        if (lobbyOverlay) lobbyOverlay.hidden = false;
        if (lobbyCountdownBanner) lobbyCountdownBanner.hidden = false;
        if (lobbyStatusBadge) {
          lobbyStatusBadge.textContent = 'Quest starting shortly...';
          lobbyStatusBadge.className = 'status-badge status-waiting';
        }
        populateLobbyDetails(state);
        stopElapsedTimer();

        const updateCountdown = () => {
          const nowServer = Date.now() + (serverOffsetMs || 0);
          const remainingSec = Math.max(0, Math.ceil((state.started_at_ms - nowServer) / 1000));
          if (lobbyCountdownSec) lobbyCountdownSec.textContent = remainingSec;
          if (remainingSec <= 0) {
            clearInterval(countdownInterval);
            countdownInterval = null;
            showActiveGameScreen(state);
          }
        };
        updateCountdown();
        countdownInterval = setInterval(updateCountdown, 1000);
      } else {
        // Countdown finished, hunt is live
        showActiveGameScreen(state);
      }
    } else if (state.game_state === 'ended') {
      releaseWakeLock();
      showActiveGameScreen(state);
      stopElapsedTimer();
      if (clueTargetLabel) clueTargetLabel.textContent = 'Ended';
      if (clueTextEl) clueTextEl.textContent = 'The quest has concluded! Thank you for participating.';
    }
  }

  function showActiveGameScreen(state) {
    if (lobbyOverlay) lobbyOverlay.hidden = true;
    if (authOverlay) authOverlay.hidden = true;

    if (statusBar) statusBar.hidden = false;
    if (clueCard) clueCard.hidden = false;
    if (gameTabBar) gameTabBar.hidden = false;

    // Manage screen wake lock while quest is active
    if (state.finished) {
      releaseWakeLock();
    } else {
      requestWakeLock();
    }

    // Update status chips
    const cleared = state.cleared || 0;
    const total = state.total || 0;
    if (statusClearedEl) statusClearedEl.textContent = `Cleared ${cleared}/${total}`;

    // Update Clue Card
    if (state.finished) {
      if (clueTargetLabel) clueTargetLabel.textContent = 'Route Complete';
      if (clueTextEl) clueTextEl.textContent = 'All checkpoints cleared! Superb run!';
      showFinishScreen();
    } else if (state.current_clue) {
      if (clueTargetLabel) clueTargetLabel.textContent = `Checkpoint #${cleared + 1}`;
      if (clueTextEl) clueTextEl.textContent = state.current_clue;
    }

    // Update Team info panel
    populateTeamPanel(state);

    // Update Cleared Checkpoints on Leaflet map
    renderClearedMarkers(state.cleared_checkpoints || []);

    // Update Route History Drawer
    renderRouteHistory(state.cleared_checkpoints || []);

    // Update Power-up tray & HUD
    if (powerupTray) {
      powerupTray.hidden = Boolean(state.finished);
    }

    // Hint power-up UI
    if (btnPowerupHint && powerupHintBadge) {
      if (state.active_hint) {
        powerupHintBadge.textContent = 'Active';
        powerupHintBadge.className = 'powerup-badge';
        btnPowerupHint.classList.add('active');
        if (clueHintBox && clueHintText) {
          clueHintBox.hidden = false;
          clueHintText.textContent = state.active_hint;
        }
      } else {
        powerupHintBadge.textContent = '+3m';
        powerupHintBadge.className = 'powerup-badge badge-penalty';
        btnPowerupHint.classList.remove('active');
        if (clueHintBox) clueHintBox.hidden = true;
      }
    }

    // Radar power-up UI
    if (btnPowerupRadar && powerupRadarBadge) {
      btnPowerupRadar.disabled = (state.radar_left || 0) <= 0 && !state.radar_active;
      if (state.radar_active) {
        powerupRadarBadge.textContent = `x${state.radar_left || 0} (${state.radar_left_s || 0}s)`;
        btnPowerupRadar.classList.add('active');
        if (hudRadarBadge) hudRadarBadge.hidden = false;
      } else {
        powerupRadarBadge.textContent = `x${state.radar_left || 0}`;
        btnPowerupRadar.classList.remove('active');
        if (hudRadarBadge) hudRadarBadge.hidden = true;
      }
    }

    // Boost power-up UI
    if (btnPowerupBoost && powerupBoostBadge) {
      btnPowerupBoost.disabled = (state.boost_left || 0) <= 0 && !state.boost_active;
      if (state.boost_active) {
        powerupBoostBadge.textContent = `x${state.boost_left || 0} (${state.boost_left_s || 0}s)`;
        btnPowerupBoost.classList.add('active');
        if (hudBoostBadge) {
          hudBoostBadge.hidden = false;
          if (hudBoostSec) hudBoostSec.textContent = state.boost_left_s || 0;
        }
      } else {
        powerupBoostBadge.textContent = `x${state.boost_left || 0}`;
        btnPowerupBoost.classList.remove('active');
        if (hudBoostBadge) hudBoostBadge.hidden = true;
      }
    }

    // Skip checkpoint UI
    if (btnSkipClue) {
      btnSkipClue.hidden = Boolean(state.finished || !state.can_skip);
    }

    // Start elapsed timer driven by server start time
    if (!state.finished) {
      startElapsedTimer(state.started_at_ms);
      // Start background location pinging
      startPinging();
    } else {
      stopElapsedTimer();
    }
  }

  function showFinishScreen() {
    if (!finishOverlay) return;
    if (unlockOverlay) unlockOverlay.hidden = true;
    finishOverlay.hidden = false;
    stopElapsedTimer();

    fetchLeaderboard().then((data) => {
      if (data && currentGameState) {
        const myTeam = data.find((t) => (currentGameState.code && t.code === currentGameState.code) || t.name === currentGameState.name);
        if (myTeam) {
          if (finishFinalRank) finishFinalRank.textContent = `#${myTeam.rank}`;
          if (finishFinalTime) finishFinalTime.textContent = myTeam.adjusted_time;
        }
      }
    });
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

  function populateTeamPanel(state) {
    if (teamInfoName) teamInfoName.textContent = state.name || 'Your Team';
    if (teamInfoCode) teamInfoCode.textContent = state.code || '---';
    if (teamInfoDevice && state.device_status) {
      teamInfoDevice.textContent = state.device_status;
    }

    if (teamInfoMembers) {
      teamInfoMembers.innerHTML = '';
      (state.members || []).forEach((member) => {
        const li = document.createElement('li');
        li.className = 'member-chip';
        li.textContent = member;
        teamInfoMembers.appendChild(li);
      });
    }
  }

  function renderClearedMarkers(clearedList) {
    if (!mapInstance) return;

    clearedList.forEach((cp) => {
      if (!clearedMarkersMap.has(cp.id)) {
        const pinIcon = L.divIcon({
          className: 'cleared-tick-pin',
          html: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>',
          iconSize: [28, 28],
          iconAnchor: [14, 14],
          popupAnchor: [0, -14],
        });

        const marker = L.marker([cp.lat, cp.lng], { icon: pinIcon }).addTo(mapInstance);
        const popupContent = `
          <div style="font-family: var(--font-stack); padding: 4px; max-width: 200px;">
            <strong style="color: var(--text); font-size: 14px;">${escapeHtml(cp.name)}</strong>
            ${cp.story ? `<p style="margin: 4px 0 0 0; font-size: 12px; color: var(--text-secondary); line-height: 1.4;">${escapeHtml(cp.story)}</p>` : ''}
          </div>
        `;
        marker.bindPopup(popupContent);
        clearedMarkersMap.set(cp.id, marker);
      }
    });
  }

  function renderRouteHistory(clearedList) {
    if (!historyItemsContainer) return;

    if (!clearedList || clearedList.length === 0) {
      historyItemsContainer.innerHTML = `
        <p class="empty-history-note">No checkpoints cleared yet. Follow your clue and walk to the first location!</p>
      `;
      return;
    }

    let html = '';
    clearedList.forEach((cp, idx) => {
      const pos = cp.position || (idx + 1);
      html += `
        <div class="history-item-card">
          <div class="history-item-title-row">
            <span class="history-tick-icon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </span>
            <span class="history-item-name">#${pos} ${escapeHtml(cp.name)}</span>
          </div>
          ${cp.story ? `<p class="history-item-story">${escapeHtml(cp.story)}</p>` : ''}
        </div>
      `;
    });
    historyItemsContainer.innerHTML = html;
  }

  function showUnlockModal(checkpointName, story, nextClue) {
    if (unlockCpName) unlockCpName.textContent = checkpointName;

    if (story && unlockStoryText && unlockStoryBox) {
      unlockStoryText.textContent = story;
      unlockStoryBox.hidden = false;
    } else if (unlockStoryBox) {
      unlockStoryBox.hidden = true;
    }

    if (unlockOverlay) unlockOverlay.hidden = false;

    // Immediately update clue card if next clue is available
    if (nextClue && clueTextEl) {
      clueTextEl.textContent = nextClue;
    }
  }

  // --- Elapsed Game Time Tick ---

  function startElapsedTimer(startedAtMs) {
    if (!startedAtMs || elapsedTimer) return;

    const tick = () => {
      const nowServer = Date.now() + (serverOffsetMs || 0);
      const elapsedS = Math.max(0, Math.floor((nowServer - startedAtMs) / 1000));
      const mins = String(Math.floor(elapsedS / 60)).padStart(2, '0');
      const secs = String(elapsedS % 60).padStart(2, '0');
      if (statusTimerEl) statusTimerEl.textContent = `${mins}:${secs}`;

      // Decrement active power-up timers live every second
      if (currentGameState) {
        if (currentGameState.boost_active && typeof currentGameState.boost_left_s === 'number') {
          currentGameState.boost_left_s = Math.max(0, currentGameState.boost_left_s - 1);
          if (currentGameState.boost_left_s <= 0) {
            currentGameState.boost_active = false;
            if (btnPowerupBoost) btnPowerupBoost.classList.remove('active');
            if (hudBoostBadge) hudBoostBadge.hidden = true;
            if (powerupBoostBadge) powerupBoostBadge.textContent = `x${currentGameState.boost_left || 0}`;
          } else {
            if (hudBoostSec) hudBoostSec.textContent = currentGameState.boost_left_s;
            if (powerupBoostBadge) powerupBoostBadge.textContent = `x${currentGameState.boost_left || 0} (${currentGameState.boost_left_s}s)`;
          }
        }
        if (currentGameState.radar_active && typeof currentGameState.radar_left_s === 'number') {
          currentGameState.radar_left_s = Math.max(0, currentGameState.radar_left_s - 1);
          if (currentGameState.radar_left_s <= 0) {
            currentGameState.radar_active = false;
            if (btnPowerupRadar) btnPowerupRadar.classList.remove('active');
            if (hudRadarBadge) hudRadarBadge.hidden = true;
            if (powerupRadarBadge) powerupRadarBadge.textContent = `x${currentGameState.radar_left || 0}`;
          } else {
            if (powerupRadarBadge) powerupRadarBadge.textContent = `x${currentGameState.radar_left || 0} (${currentGameState.radar_left_s}s)`;
          }
        }
      }
    };

    tick();
    elapsedTimer = setInterval(tick, 1000);
  }

  function stopElapsedTimer() {
    if (elapsedTimer) {
      clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
  }

  // --- Background GPS Pinging ---

  function startPinging() {
    if (pingTimer) return;

    pingTimer = setInterval(() => {
      if (!currentGameState || currentGameState.game_state !== 'running' || currentGameState.finished) {
        return;
      }

      const nowServer = Date.now() + (serverOffsetMs || 0);
      if (currentGameState.started_at_ms && nowServer < currentGameState.started_at_ms) {
        return;
      }

      if (!latestFix || latestFix.ts <= lastSentFixTs) {
        return;
      }

      lastSentFixTs = latestFix.ts;

      fetch('/api/ping', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lat: latestFix.lat,
          lng: latestFix.lng,
          accuracy: latestFix.accuracy,
          ts: latestFix.ts,
        }),
      })
        .then(async (res) => {
          hideReconnecting();
          if (!res.ok) {
            if (res.status === 401) {
              handleUnauthorized();
              return null;
            }
            return null;
          }
          return res.json();
        })
        .then((data) => {
          if (!data) return;

          if (data.status === 'unlocked') {
            showUnlockModal(data.checkpoint_name || 'Checkpoint', data.story, data.next_clue);
            if (data.awarded_powerup) {
              const label = data.awarded_powerup === 'radar' ? 'Radar' : 'Radius Boost';
              showPowerupToast(`🎉 Awarded 1 ${label}!`);
            }
            // Refresh full state to sync cleared checkpoints & counts
            fetchState();
          } else if (data.status === 'weak_gps') {
            const acc = (latestFix && latestFix.accuracy) ? Math.round(latestFix.accuracy) : null;
            const accText = acc ? ` (${acc}m)` : '';
            setGpsStatus(`GPS weak${accText} - Move to open area`, 'chip-weak');
          } else if (data.status === 'implausible') {
            setGpsStatus('Speed too high / teleporting', 'chip-weak');
          } else if (data.status === 'completed') {
            fetchState();
            showFinishScreen();
          }

          // Live Radar distance update
          if (data.radar_distance_m !== undefined || data.radar_label) {
            if (hudRadarBadge && hudRadarText) {
              hudRadarBadge.hidden = false;
              hudRadarText.textContent = data.radar_label || `${data.radar_distance_m} m`;
            }
          }
        })
        .catch(() => {
          showReconnecting('Server unreachable. Reconnecting automatically...');
        });
    }, pingIntervalMs);
  }

  // --- Power-up Actions & Handlers ---

  function showPowerupToast(msg) {
    if (!powerupToast) return;
    powerupToast.textContent = msg;
    powerupToast.hidden = false;
    setTimeout(() => {
      powerupToast.hidden = true;
    }, 3500);
  }

  function activatePowerup(type) {
    return fetch(`/api/powerup/${type}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(body.detail || `Failed to activate ${type}`);
        }
        return body;
      })
      .then((data) => {
        if (type === 'hint') {
          showPowerupToast('💡 Hint revealed (+3 min added)');
        } else if (type === 'radar') {
          showPowerupToast('📡 Radar active! Tracking live distance for 60s');
        } else if (type === 'boost') {
          showPowerupToast('⚡ Radius boost active! +30% radius for 120s');
        }
        fetchState();
      })
      .catch((err) => {
        showPowerupToast(err.message || 'Power-up unavailable');
      });
  }

  if (btnPowerupHint) {
    btnPowerupHint.addEventListener('click', () => {
      if (currentGameState && currentGameState.active_hint) {
        showPowerupToast('Hint already revealed for this checkpoint');
        return;
      }
      if (hintConfirmOverlay) hintConfirmOverlay.hidden = false;
    });
  }

  if (btnHintCancel) {
    btnHintCancel.addEventListener('click', () => {
      if (hintConfirmOverlay) hintConfirmOverlay.hidden = true;
    });
  }

  if (btnHintConfirm) {
    btnHintConfirm.addEventListener('click', () => {
      if (hintConfirmOverlay) hintConfirmOverlay.hidden = true;
      activatePowerup('hint');
    });
  }

  if (btnPowerupRadar) {
    btnPowerupRadar.addEventListener('click', () => {
      activatePowerup('radar');
    });
  }

  if (btnPowerupBoost) {
    btnPowerupBoost.addEventListener('click', () => {
      activatePowerup('boost');
    });
  }

  // --- Skip Checkpoint Handlers ---

  function handleSkipCheckpoint() {
    if (btnSkipConfirm) btnSkipConfirm.disabled = true;
    fetch('/api/skip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(body.detail || 'Failed to skip checkpoint');
        }
        return body;
      })
      .then((data) => {
        showPowerupToast('⏭️ Checkpoint skipped (+10 min penalty added)');
        if (skipConfirmOverlay) skipConfirmOverlay.hidden = true;
        if (btnSkipClue) btnSkipClue.hidden = true;
        fetchState();
      })
      .catch((err) => {
        showPowerupToast(err.message || 'Skip unavailable');
      })
      .finally(() => {
        if (btnSkipConfirm) btnSkipConfirm.disabled = false;
      });
  }

  if (btnSkipClue) {
    btnSkipClue.addEventListener('click', () => {
      if (skipConfirmOverlay) skipConfirmOverlay.hidden = false;
    });
  }

  if (btnSkipCancel) {
    btnSkipCancel.addEventListener('click', () => {
      if (skipConfirmOverlay) skipConfirmOverlay.hidden = true;
    });
  }

  if (btnSkipConfirm) {
    btnSkipConfirm.addEventListener('click', () => {
      handleSkipCheckpoint();
    });
  }

  // --- Session Restoration & Background Polling ---

  function fetchState() {
    return fetch('/api/state')
      .then((res) => {
        hideReconnecting();
        if (res.ok) return res.json();
        if (res.status === 401) {
          handleUnauthorized();
          return null;
        }
        return null;
      })
      .then((state) => {
        if (state) updateGameState(state);
      })
      .catch(() => {
        showReconnecting('Server unreachable. Reconnecting automatically...');
      });
  }

  function handleUnauthorized() {
    releaseWakeLock();
    if (pollingTimer) {
      clearInterval(pollingTimer);
      pollingTimer = null;
    }
    if (pingTimer) {
      clearInterval(pingTimer);
      pingTimer = null;
    }
    stopElapsedTimer();

    if (authOverlay) authOverlay.hidden = false;
    if (lobbyOverlay) lobbyOverlay.hidden = true;
    if (statusBar) statusBar.hidden = true;
    if (clueCard) clueCard.hidden = true;
    if (powerupTray) powerupTray.hidden = true;
    if (hintConfirmOverlay) hintConfirmOverlay.hidden = true;
    if (skipConfirmOverlay) skipConfirmOverlay.hidden = true;
    if (btnSkipClue) btnSkipClue.hidden = true;
    if (clueHintBox) clueHintBox.hidden = true;
    if (gameTabBar) gameTabBar.hidden = true;
    if (viewTeam) viewTeam.hidden = true;
    if (viewLeaderboard) viewLeaderboard.hidden = true;
    if (finishOverlay) finishOverlay.hidden = true;
  }

  function startPolling() {
    if (pollingTimer) clearInterval(pollingTimer);
    pollingTimer = setInterval(() => {
      fetchState();
      if ((viewLeaderboard && !viewLeaderboard.hidden) || (finishOverlay && !finishOverlay.hidden)) {
        fetchLeaderboard();
      }
    }, pollIntervalMs);
  }

  function checkSession() {
    fetch('/api/state')
      .then((res) => {
        hideReconnecting();
        if (res.ok) {
          return res.json().then((state) => {
            updateGameState(state);
            startPolling();
          });
        }
        if (res.status === 401) {
          handleUnauthorized();
        }
      })
      .catch(() => {
        handleUnauthorized();
      });
  }

  // Always verify server session on page load
  checkSession();

  // --- Map & Geolocation Initialization ---

  fetch('/api/config')
    .then((response) => {
      if (!response.ok) {
        throw new Error('Server returned status ' + response.status);
      }
      return response.json();
    })
    .then((cfg) => {
      if (cfg.ping_interval_ms) pingIntervalMs = cfg.ping_interval_ms;
      if (cfg.poll_interval_ms) pollIntervalMs = cfg.poll_interval_ms;
      if (typeof cfg.test_mode === 'boolean') setTestMode(cfg.test_mode);
      initMap(cfg);
    })
    .catch((err) => {
      setGpsStatus('Map config failed: ' + err.message, 'chip-weak');
    });

  function initMap(cfg) {
    const sw = L.latLng(cfg.bounds.sw.lat, cfg.bounds.sw.lng);
    const ne = L.latLng(cfg.bounds.ne.lat, cfg.bounds.ne.lng);
    campusBounds = L.latLngBounds(sw, ne);

    mapInstance = L.map('map', {
      center: [cfg.center.lat, cfg.center.lng],
      zoom: cfg.zoom.start,
      minZoom: cfg.zoom.min,
      maxZoom: cfg.zoom.max,
      maxBounds: campusBounds,
      maxBoundsViscosity: 1.0,
      zoomControl: false,
    });

    // Place zoom control at bottom-right above tab bar
    L.control.zoom({ position: 'bottomright' }).addTo(mapInstance);

    L.tileLayer(cfg.tile_url, {
      attribution: cfg.tile_attribution,
      minZoom: cfg.zoom.min,
      maxZoom: cfg.zoom.max,
    }).addTo(mapInstance);

    // Map click in test mode: simulates player location ping
    mapInstance.on('click', (e) => {
      if (isTestModeActive) {
        sendSimulatedPing(e.latlng.lat, e.latlng.lng);
      }
    });

    // If game state was already fetched before map initialized, render cleared markers
    if (currentGameState && currentGameState.cleared_checkpoints) {
      renderClearedMarkers(currentGameState.cleared_checkpoints);
    }

    if (btnRetryGps) {
      btnRetryGps.addEventListener('click', () => {
        if ('geolocation' in navigator) {
          navigator.geolocation.getCurrentPosition(
            onLocationSuccess,
            onLocationError,
            { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
          );
        }
      });
    }

    if (!('geolocation' in navigator)) {
      setGpsStatus('Geolocation not supported', 'chip-weak');
      if (gpsPermissionGuide) {
        const text = gpsPermissionGuide.querySelector('.banner-text');
        if (text) {
          text.innerHTML = '<strong>Geolocation unsupported.</strong><p class="banner-subtext">Your browser or device does not support GPS location tracking.</p>';
        }
        gpsPermissionGuide.hidden = false;
      }
      return;
    }

    setGpsStatus('Waiting for GPS...', 'chip-waiting');

    function onLocationSuccess(position) {
      if (gpsPermissionGuide) {
        gpsPermissionGuide.hidden = true;
      }
      const lat = position.coords.latitude;
      const lng = position.coords.longitude;
      const accuracy = position.coords.accuracy;
      const latLng = [lat, lng];

      updatePlayerLocation(lat, lng, accuracy);
      latestFix.ts = position.timestamp || Date.now();

      if (!initialFixApplied) {
        if (campusBounds.contains(latLng)) {
          mapInstance.panTo(latLng);
        }
        initialFixApplied = true;
      }

      // ACCURACY_LIMIT_M = 30.0m
      const roundedAcc = Math.round(accuracy);
      if (accuracy <= 30.0) {
        setGpsStatus(`GPS good (${roundedAcc}m)`, 'chip-good');
      } else {
        setGpsStatus(`GPS weak (${roundedAcc}m) - Move to open area`, 'chip-weak');
      }
    }

    function onLocationError(error) {
      let message = 'Unable to determine position.';
      if (error.code === error.PERMISSION_DENIED) {
        message = 'Location permission denied';
        if (gpsPermissionGuide) {
          const text = gpsPermissionGuide.querySelector('.banner-text');
          if (text) {
            text.innerHTML = '<strong>Location permission denied.</strong><p class="banner-subtext">Tap the lock or settings icon in your browser address bar, set Location to <strong>Allow</strong>, and reload this page.</p>';
          }
          gpsPermissionGuide.hidden = false;
        }
      } else if (error.code === error.POSITION_UNAVAILABLE) {
        message = 'GPS unavailable - Move outdoors';
        if (gpsPermissionGuide) {
          const text = gpsPermissionGuide.querySelector('.banner-text');
          if (text) {
            text.innerHTML = '<strong>GPS signal unavailable.</strong><p class="banner-subtext">Move outdoors with an open sky view away from large concrete buildings.</p>';
          }
          gpsPermissionGuide.hidden = false;
        }
      } else if (error.code === error.TIMEOUT) {
        message = 'Waiting for GPS fix (timed out)...';
      }
      setGpsStatus(message, 'chip-weak');
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
