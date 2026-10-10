/**
 * Campus Quest - Admin Panel Frontend Logic (/gods)
 *
 * Communicates with /api/gods endpoints using signed HttpOnly session cookies.
 * Does not store any credentials or game state in localStorage/sessionStorage.
 */

document.addEventListener("DOMContentLoaded", () => {
  // Elements: Auth & Shell
  const loginSection = document.getElementById("login-section");
  const adminShellSection = document.getElementById("admin-shell-section");
  const loginForm = document.getElementById("login-form");
  const usernameInput = document.getElementById("admin-username-input");
  const passwordInput = document.getElementById("admin-password-input");
  const loginBtn = document.getElementById("login-submit-btn");
  const logoutBtn = document.getElementById("logout-btn");
  const loginAlert = document.getElementById("login-alert");
  const currentAdminName = document.getElementById("current-admin-name");

  // Elements: Tabs
  const tabBtnGame = document.getElementById("tab-btn-game");
  const tabBtnCheckpoints = document.getElementById("tab-btn-checkpoints");
  const tabBtnTeams = document.getElementById("tab-btn-teams");
  const tabPanelGame = document.getElementById("tab-panel-game");
  const tabPanelCheckpoints = document.getElementById("tab-panel-checkpoints");
  const tabPanelTeams = document.getElementById("tab-panel-teams");

  // Elements: Teams Tab
  const teamsAlert = document.getElementById("gods-teams-alert");
  const teamsCounterPill = document.getElementById("teams-counter-pill");
  const btnRefreshTeams = document.getElementById("btn-refresh-teams");
  const teamsTableBody = document.getElementById("teams-table-body");

  // Elements: Adjust Modal
  const adjustModal = document.getElementById("adjust-modal");
  const adjustTeamName = document.getElementById("adjust-team-name");
  const adjustModalAlert = document.getElementById("adjust-modal-alert");
  const adjustForm = document.getElementById("adjust-form");
  const adjustTeamId = document.getElementById("adjust-team-id");
  const adjustMinutesInput = document.getElementById("adjust-minutes-input");
  const adjustReasonInput = document.getElementById("adjust-reason-input");
  const btnAdjustCancel = document.getElementById("btn-adjust-cancel");
  const btnAdjustModalClose = document.getElementById("btn-adjust-modal-close");

  // Elements: Delete Modal
  const deleteModal = document.getElementById("delete-modal");
  const deleteModalWarning = document.getElementById("delete-modal-warning");
  const deleteModalAlert = document.getElementById("delete-modal-alert");
  const btnDeleteCancel = document.getElementById("btn-delete-cancel");
  const btnDeleteModalClose = document.getElementById("btn-delete-modal-close");
  const btnDeleteConfirm = document.getElementById("btn-delete-confirm");

  // Elements: Clear Checkpoint Modal
  const clearModal = document.getElementById("clear-modal");
  const clearTeamName = document.getElementById("clear-team-name");
  const clearModalAlert = document.getElementById("clear-modal-alert");
  const clearForm = document.getElementById("clear-form");
  const clearTeamId = document.getElementById("clear-team-id");
  const clearReasonInput = document.getElementById("clear-reason-input");
  const btnClearCancel = document.getElementById("btn-clear-cancel");
  const btnClearModalClose = document.getElementById("btn-clear-modal-close");

  // Elements: Game Tab
  const gameAlert = document.getElementById("gods-game-alert");
  const gameStateBadge = document.getElementById("game-state-badge");
  const gameCountdownBanner = document.getElementById("game-countdown-banner");
  const gameCountdownSec = document.getElementById("game-countdown-sec");
  const gameStateDesc = document.getElementById("game-state-desc");
  const btnGameStart = document.getElementById("btn-game-start");
  const btnGameEnd = document.getElementById("btn-game-end");
  const btnGameReset = document.getElementById("btn-game-reset");
  const startDisabledReason = document.getElementById("start-disabled-reason");
  const regStatusBadge = document.getElementById("reg-status-badge");
  const regStatusDesc = document.getElementById("reg-status-desc");
  const btnToggleRegistration = document.getElementById("btn-toggle-registration");
  const gameCpCounter = document.getElementById("game-cp-counter");
  const gameCpStatusText = document.getElementById("game-cp-status-text");
  const btnSwitchToCheckpoints = document.getElementById("btn-switch-to-checkpoints");

  // Elements: Checkpoints Workspace
  const globalAlert = document.getElementById("gods-global-alert");
  const counterPill = document.getElementById("cp-counter-pill");
  const checkpointsList = document.getElementById("checkpoints-list");
  const checkpointsEmpty = document.getElementById("checkpoints-empty");
  const cpFormCard = document.getElementById("cp-form-card");
  const cpFormTitle = document.getElementById("cp-form-title");
  const cpForm = document.getElementById("cp-form");
  const cpIdInput = document.getElementById("cp-id");
  const cpNameInput = document.getElementById("cp-name");
  const cpLatInput = document.getElementById("cp-lat");
  const cpLngInput = document.getElementById("cp-lng");
  const cpRadiusInput = document.getElementById("cp-radius");
  const cpPositionInput = document.getElementById("cp-position");
  const cpClueInput = document.getElementById("cp-clue");
  const cpHintInput = document.getElementById("cp-hint");
  const cpStoryInput = document.getElementById("cp-story");
  const cpFormAlert = document.getElementById("cp-form-alert");
  const cpFormSaveBtn = document.getElementById("cp-form-save-btn");
  const cpFormCancelBtn = document.getElementById("cp-form-cancel-btn");
  const btnAddCheckpoint = document.getElementById("btn-add-checkpoint");
  const btnAddCheckpointList = document.getElementById("btn-add-checkpoint-list");

  // State
  let mapInstance = null;
  let campusConfig = null;
  let checkpointsData = [];
  let mapMarkers = new Map(); // id -> { marker, circle }
  let draftMarker = null;
  let draftCircle = null;
  let isMapInitialized = false;
  let currentGameStatus = null;
  let countdownTimerInterval = null;
  let teamsData = [];
  let teamsRefreshInterval = null;
  let gameStatusRefreshInterval = null;
  let pendingDeleteTeamId = null;

  function showLoginAlert(message, isError = true) {
    if (!loginAlert) return;
    loginAlert.textContent = message;
    loginAlert.hidden = false;
    loginAlert.className = isError ? "gods-alert gods-alert-error" : "gods-alert gods-alert-success";
  }

  function hideLoginAlert() {
    if (!loginAlert) return;
    loginAlert.textContent = "";
    loginAlert.hidden = true;
  }

  function showGlobalAlert(message, isError = true) {
    if (!globalAlert) return;
    globalAlert.textContent = message;
    globalAlert.hidden = false;
    globalAlert.className = isError ? "gods-alert gods-alert-error" : "gods-alert gods-alert-success";
  }

  function hideGlobalAlert() {
    if (!globalAlert) return;
    globalAlert.textContent = "";
    globalAlert.hidden = true;
  }

  function showTeamsAlert(message, isError = true) {
    if (!teamsAlert) return;
    teamsAlert.textContent = message;
    teamsAlert.hidden = false;
    teamsAlert.className = isError ? "gods-alert gods-alert-error" : "gods-alert gods-alert-success";
  }

  function hideTeamsAlert() {
    if (!teamsAlert) return;
    teamsAlert.textContent = "";
    teamsAlert.hidden = true;
  }

  function showFormAlert(message) {
    if (!cpFormAlert) return;
    cpFormAlert.textContent = message;
    cpFormAlert.hidden = false;
  }

  function hideFormAlert() {
    if (!cpFormAlert) return;
    cpFormAlert.textContent = "";
    cpFormAlert.hidden = true;
  }

  function showGameAlert(message, isError = true) {
    if (!gameAlert) return;
    gameAlert.textContent = message;
    gameAlert.hidden = false;
    gameAlert.className = isError ? "gods-alert gods-alert-error" : "gods-alert gods-alert-success";
  }

  function hideGameAlert() {
    if (!gameAlert) return;
    gameAlert.textContent = "";
    gameAlert.hidden = true;
  }

  function switchTab(tabName) {
    hideGameAlert();
    hideGlobalAlert();
    hideTeamsAlert();

    const isGame = tabName === "game";
    const isCheckpoints = tabName === "checkpoints";
    const isTeams = tabName === "teams";

    if (tabBtnGame) {
      tabBtnGame.classList.toggle("active", isGame);
      tabBtnGame.setAttribute("aria-selected", isGame ? "true" : "false");
    }
    if (tabBtnCheckpoints) {
      tabBtnCheckpoints.classList.toggle("active", isCheckpoints);
      tabBtnCheckpoints.setAttribute("aria-selected", isCheckpoints ? "true" : "false");
    }
    if (tabBtnTeams) {
      tabBtnTeams.classList.toggle("active", isTeams);
      tabBtnTeams.setAttribute("aria-selected", isTeams ? "true" : "false");
    }

    if (tabPanelGame) {
      tabPanelGame.hidden = !isGame;
    }
    if (tabPanelCheckpoints) {
      tabPanelCheckpoints.hidden = !isCheckpoints;
    }
    if (tabPanelTeams) {
      tabPanelTeams.hidden = !isTeams;
    }

    if (isGame) {
      loadGameStatus();
      if (!gameStatusRefreshInterval) {
        gameStatusRefreshInterval = setInterval(loadGameStatus, 5000);
      }
    } else {
      if (gameStatusRefreshInterval) {
        clearInterval(gameStatusRefreshInterval);
        gameStatusRefreshInterval = null;
      }
    }

    if (isCheckpoints) {
      loadCheckpoints();
      if (mapInstance) {
        setTimeout(() => mapInstance.invalidateSize(), 120);
      }
    }

    if (isTeams) {
      loadAdminTeams();
      if (!teamsRefreshInterval) {
        teamsRefreshInterval = setInterval(loadAdminTeams, 5000);
      }
    } else {
      if (teamsRefreshInterval) {
        clearInterval(teamsRefreshInterval);
        teamsRefreshInterval = null;
      }
    }
  }

  async function loadGameStatus() {
    try {
      const res = await fetch("/api/gods/game/status", {
        headers: { "Accept": "application/json" },
      });
      if (!res.ok) {
        throw new Error("Failed to load game status.");
      }
      const data = await res.json();
      currentGameStatus = data;
      renderGameStatus(data);
    } catch (err) {
      showGameAlert("Status fetch error: " + err.message, true);
    }
  }

  function renderGameStatus(status) {
    if (!status) return;

    // 1. Current State Badge
    if (gameStateBadge) {
      gameStateBadge.textContent = status.game_state;
      gameStateBadge.className = `badge-status badge-${status.game_state}`;
    }

    // Countdown / status descriptions
    if (countdownTimerInterval) {
      clearInterval(countdownTimerInterval);
      countdownTimerInterval = null;
    }

    if (status.game_state === "running") {
      if (gameStateDesc) {
        gameStateDesc.textContent = "The quest is live. Checkpoint positions and order are locked.";
      }
      const serverOffsetMs = status.server_now_ms - Date.now();
      const currentServerTime = Date.now() + serverOffsetMs;
      if (status.started_at_ms && currentServerTime < status.started_at_ms) {
        if (gameCountdownBanner) gameCountdownBanner.hidden = false;
        const updateCountdown = () => {
          const nowServer = Date.now() + serverOffsetMs;
          const remainingSec = Math.max(0, Math.ceil((status.started_at_ms - nowServer) / 1000));
          if (gameCountdownSec) gameCountdownSec.textContent = remainingSec;
          if (remainingSec <= 0) {
            if (gameCountdownBanner) gameCountdownBanner.hidden = true;
            clearInterval(countdownTimerInterval);
            countdownTimerInterval = null;
          }
        };
        updateCountdown();
        countdownTimerInterval = setInterval(updateCountdown, 1000);
      } else {
        if (gameCountdownBanner) gameCountdownBanner.hidden = true;
      }
    } else if (status.game_state === "ended") {
      if (gameStateDesc) {
        gameStateDesc.textContent = "The game has ended. Results are finalized.";
      }
      if (gameCountdownBanner) gameCountdownBanner.hidden = true;
    } else {
      if (gameStateDesc) {
        gameStateDesc.textContent = "The game is in setup. Configure checkpoints and open registration when ready.";
      }
      if (gameCountdownBanner) gameCountdownBanner.hidden = true;
    }

    // 2. Registration status
    if (regStatusBadge) {
      const isOpen = status.registration_open;
      regStatusBadge.textContent = isOpen ? "Open" : "Closed";
      regStatusBadge.className = `badge-status ${isOpen ? "badge-open" : "badge-closed"}`;
    }
    if (btnToggleRegistration) {
      btnToggleRegistration.textContent = status.registration_open ? "Close Registration" : "Open Registration";
      btnToggleRegistration.disabled = (status.game_state === "ended");
    }

    // 3. Checkpoint Readiness Counter
    const cpCount = status.checkpoint_count;
    const minCp = status.min_checkpoints;
    if (gameCpCounter) {
      gameCpCounter.textContent = `${cpCount} of ${minCp} needed`;
      gameCpCounter.className = cpCount >= minCp ? "counter-pill counter-satisfied" : "counter-pill";
    }
    if (gameCpStatusText) {
      if (cpCount >= minCp) {
        gameCpStatusText.textContent = `Ready! You have ${cpCount} checkpoints configured (minimum is ${minCp}).`;
      } else {
        gameCpStatusText.textContent = `Need ${minCp - cpCount} more checkpoint(s) before game can start.`;
      }
    }

    // 4. Start & End Button availability & reasons
    if (btnGameStart) {
      if (status.game_state === "running") {
        btnGameStart.disabled = true;
        if (startDisabledReason) {
          startDisabledReason.textContent = "Game is already running.";
          startDisabledReason.hidden = false;
        }
      } else if (status.game_state === "ended") {
        btnGameStart.disabled = true;
        if (startDisabledReason) {
          startDisabledReason.textContent = "Game has ended.";
          startDisabledReason.hidden = false;
        }
      } else if (cpCount < minCp) {
        btnGameStart.disabled = true;
        if (startDisabledReason) {
          startDisabledReason.textContent = `Cannot start: configure at least ${minCp} checkpoints (currently ${cpCount}).`;
          startDisabledReason.hidden = false;
        }
      } else {
        btnGameStart.disabled = false;
        if (startDisabledReason) {
          startDisabledReason.textContent = "";
          startDisabledReason.hidden = true;
        }
      }
    }

    if (btnGameEnd) {
      btnGameEnd.disabled = (status.game_state !== "running");
    }

    if (btnGameReset) {
      btnGameReset.disabled = (status.game_state === "setup");
    }
  }

  async function handleToggleRegistration() {
    if (!currentGameStatus) return;
    hideGameAlert();
    const action = currentGameStatus.registration_open ? "close" : "open";
    try {
      const res = await fetch(`/api/gods/registration/${action}`, {
        method: "POST",
        headers: { "Accept": "application/json" },
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to ${action} registration.`);
      }
      await loadGameStatus();
      showGameAlert(`Registration successfully ${action === "open" ? "opened" : "closed"}.`, false);
    } catch (err) {
      showGameAlert("Error toggling registration: " + err.message, true);
    }
  }

  async function handleStartGame() {
    hideGameAlert();
    try {
      const res = await fetch("/api/gods/game/start", {
        method: "POST",
        headers: { "Accept": "application/json" },
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to start game.");
      }
      await loadGameStatus();
      await loadCheckpoints();
      showGameAlert("Game started! 10-second countdown is live on all devices.", false);
    } catch (err) {
      showGameAlert("Start error: " + err.message, true);
    }
  }

  async function handleEndGame() {
    const confirmed = window.confirm("Are you sure you want to end the game? This will stop the quest for all teams.");
    if (!confirmed) return;

    hideGameAlert();
    try {
      const res = await fetch("/api/gods/game/end", {
        method: "POST",
        headers: { "Accept": "application/json" },
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to end game.");
      }
      await loadGameStatus();
      await loadCheckpoints();
      showGameAlert("Game ended successfully.", false);
    } catch (err) {
      showGameAlert("End error: " + err.message, true);
    }
  }

  async function handleResetGame() {
    const confirmed = window.confirm("Reset game back to Setup? This will allow starting a new quest.");
    if (!confirmed) return;

    hideGameAlert();
    try {
      const res = await fetch("/api/gods/game/reset", {
        method: "POST",
        headers: { "Accept": "application/json" },
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to reset game.");
      }
      await loadGameStatus();
      await loadCheckpoints();
      showGameAlert("Game reset to setup successfully.", false);
    } catch (err) {
      showGameAlert("Reset error: " + err.message, true);
    }
  }

  function showAdminShell(username) {
    if (currentAdminName) {
      currentAdminName.textContent = username;
    }
    const container = document.querySelector(".gods-container");
    if (container) container.classList.add("gods-container-shell");
    if (loginSection) loginSection.hidden = true;
    if (adminShellSection) adminShellSection.hidden = false;
    hideLoginAlert();

    if (!isMapInitialized) {
      initAdminPanel();
    } else if (mapInstance) {
      setTimeout(() => mapInstance.invalidateSize(), 150);
    }
  }

  function showLoginForm() {
    if (teamsRefreshInterval) {
      clearInterval(teamsRefreshInterval);
      teamsRefreshInterval = null;
    }
    if (gameStatusRefreshInterval) {
      clearInterval(gameStatusRefreshInterval);
      gameStatusRefreshInterval = null;
    }
    const container = document.querySelector(".gods-container");
    if (container) container.classList.remove("gods-container-shell");
    if (adminShellSection) adminShellSection.hidden = true;
    if (loginSection) loginSection.hidden = false;
    if (passwordInput) passwordInput.value = "";
    hideGlobalAlert();
    hideTeamsAlert();
  }

  // --- Session Management ---

  async function checkSession() {
    try {
      const response = await fetch("/api/gods/me", {
        headers: { "Accept": "application/json" },
      });

      if (response.ok) {
        const data = await response.json();
        showAdminShell(data.username || "admin");
      } else {
        showLoginForm();
      }
    } catch (err) {
      showLoginForm();
      showLoginAlert("Could not connect to server. Check your network.", true);
    }
  }

  if (loginForm) {
    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      hideLoginAlert();

      const username = usernameInput ? usernameInput.value.trim() : "";
      const password = passwordInput ? passwordInput.value : "";

      if (!username || !password) {
        showLoginAlert("Please enter both User ID and password.", true);
        return;
      }

      if (loginBtn) {
        loginBtn.disabled = true;
        loginBtn.textContent = "Logging in...";
      }

      try {
        const response = await fetch("/api/gods/login", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json",
          },
          body: JSON.stringify({ username, password }),
        });

        if (response.ok) {
          const data = await response.json();
          showAdminShell(data.username || username);
        } else if (response.status === 401) {
          showLoginAlert("Invalid User ID or password.", true);
        } else if (response.status === 429) {
          showLoginAlert("Too many failed attempts. Please wait a minute before retrying.", true);
        } else {
          showLoginAlert("Server error during login. Please try again later.", true);
        }
      } catch (err) {
        showLoginAlert("Network error. Unable to reach server.", true);
      } finally {
        if (loginBtn) {
          loginBtn.disabled = false;
          loginBtn.textContent = "Log In";
        }
      }
    });
  }

  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      logoutBtn.disabled = true;
      try {
        const response = await fetch("/api/gods/logout", {
          method: "POST",
          headers: { "Accept": "application/json" },
        });

        if (response.ok) {
          showLoginForm();
        } else {
          showLoginAlert("Logout failed on server, resetting view.", true);
          showLoginForm();
        }
      } catch (err) {
        showLoginAlert("Network error during logout.", true);
        showLoginForm();
      } finally {
        logoutBtn.disabled = false;
      }
    });
  }

  // --- Map and Checkpoint Management ---

  async function initAdminPanel() {
    isMapInitialized = true;
    try {
      const response = await fetch("/api/config");
      if (!response.ok) {
        throw new Error("Failed to load map configuration");
      }
      campusConfig = await response.json();
      initMap(campusConfig);
      await Promise.all([
        loadGameStatus(),
        loadCheckpoints(),
      ]);
      if (tabPanelGame && !tabPanelGame.hidden && !gameStatusRefreshInterval) {
        gameStatusRefreshInterval = setInterval(loadGameStatus, 5000);
      }
      setTimeout(() => {
        if (mapInstance) mapInstance.invalidateSize();
      }, 150);
    } catch (err) {
      showGlobalAlert("Failed to load admin map configuration: " + err.message, true);
    }
  }

  function initMap(cfg) {
    const mapElement = document.getElementById("gods-map");
    if (!mapElement || typeof L === "undefined") return;

    const sw = L.latLng(cfg.bounds.sw.lat, cfg.bounds.sw.lng);
    const ne = L.latLng(cfg.bounds.ne.lat, cfg.bounds.ne.lng);
    const campusBounds = L.latLngBounds(sw, ne);

    mapInstance = L.map("gods-map", {
      center: [cfg.center.lat, cfg.center.lng],
      zoom: cfg.zoom.start,
      minZoom: cfg.zoom.min,
      maxZoom: cfg.zoom.max,
      maxBounds: campusBounds,
      maxBoundsViscosity: 1.0,
      zoomControl: false,
    });

    L.control.zoom({ position: "bottomright" }).addTo(mapInstance);

    L.tileLayer(cfg.tile_url, {
      attribution: cfg.tile_attribution,
      minZoom: cfg.zoom.min,
      maxZoom: cfg.zoom.max,
    }).addTo(mapInstance);

    // Map click: drops a new checkpoint pin and opens create form
    mapInstance.on("click", (e) => {
      const lat = parseFloat(e.latlng.lat.toFixed(6));
      const lng = parseFloat(e.latlng.lng.toFixed(6));

      // Verify click falls inside campus bounds
      if (!campusBounds.contains(e.latlng)) {
        showGlobalAlert("Selected location is outside the DAVV campus boundary.", true);
        return;
      }
      hideGlobalAlert();

      startNewCheckpointDraft(lat, lng);
    });

    // Handle radius input change to update circle visual in real time
    if (cpRadiusInput) {
      cpRadiusInput.addEventListener("input", () => {
        const rad = parseFloat(cpRadiusInput.value) || 30;
        if (draftCircle) {
          draftCircle.setRadius(rad);
        }
        const activeId = parseInt(cpIdInput.value, 10);
        if (activeId && mapMarkers.has(activeId)) {
          mapMarkers.get(activeId).circle.setRadius(rad);
        }
      });
    }

    // Cancel editing
    if (cpFormCancelBtn) {
      cpFormCancelBtn.addEventListener("click", () => {
        closeCheckpointForm();
      });
    }

    // Save checkpoint form
    if (cpForm) {
      cpForm.addEventListener("submit", handleCheckpointFormSubmit);
    }

    // Explicit "+ Add Checkpoint" button handlers
    function triggerAddCheckpoint() {
      hideGlobalAlert();
      let defaultLat, defaultLng;
      if (mapInstance) {
        const center = mapInstance.getCenter();
        defaultLat = parseFloat(center.lat.toFixed(6));
        defaultLng = parseFloat(center.lng.toFixed(6));
      } else if (campusConfig && campusConfig.center) {
        defaultLat = campusConfig.center.lat;
        defaultLng = campusConfig.center.lng;
      } else {
        defaultLat = 22.680658;
        defaultLng = 75.879472;
      }

      startNewCheckpointDraft(defaultLat, defaultLng);
      if (mapInstance) {
        mapInstance.invalidateSize();
      }
      if (cpNameInput) {
        cpNameInput.focus();
      }
    }

    if (btnAddCheckpoint) {
      btnAddCheckpoint.addEventListener("click", triggerAddCheckpoint);
    }
    if (btnAddCheckpointList) {
      btnAddCheckpointList.addEventListener("click", triggerAddCheckpoint);
    }

    window.addEventListener("resize", () => {
      if (mapInstance) mapInstance.invalidateSize();
    });
  }

  function clearDraftMarker() {
    if (draftMarker && mapInstance) {
      mapInstance.removeLayer(draftMarker);
      draftMarker = null;
    }
    if (draftCircle && mapInstance) {
      mapInstance.removeLayer(draftCircle);
      draftCircle = null;
    }
  }

  function startNewCheckpointDraft(lat, lng) {
    if (currentGameStatus && currentGameStatus.game_state !== "setup") {
      showGlobalAlert("Cannot add checkpoints once the game has started.", true);
      return;
    }

    clearDraftMarker();
    hideFormAlert();

    const defaultRadius = 30;
    const nextPosition = checkpointsData.length + 1;

    // Place draggable draft pin
    draftMarker = L.marker([lat, lng], {
      draggable: true,
      title: "New Checkpoint",
    }).addTo(mapInstance);

    draftCircle = L.circle([lat, lng], {
      radius: defaultRadius,
      color: "#1a73e8",
      fillColor: "#1a73e8",
      fillOpacity: 0.15,
      weight: 2,
    }).addTo(mapInstance);

    draftMarker.on("drag", (evt) => {
      const pos = evt.target.getLatLng();
      const newLat = parseFloat(pos.lat.toFixed(6));
      const newLng = parseFloat(pos.lng.toFixed(6));
      draftCircle.setLatLng(pos);
      if (cpLatInput) cpLatInput.value = newLat;
      if (cpLngInput) cpLngInput.value = newLng;
    });

    // Populate form
    if (cpFormTitle) cpFormTitle.textContent = "Add Checkpoint";
    if (cpIdInput) cpIdInput.value = "";
    if (cpNameInput) cpNameInput.value = "";
    if (cpLatInput) cpLatInput.value = lat;
    if (cpLngInput) cpLngInput.value = lng;
    if (cpRadiusInput) {
      cpRadiusInput.value = defaultRadius;
      cpRadiusInput.disabled = false;
    }
    if (cpPositionInput) {
      cpPositionInput.value = nextPosition;
      cpPositionInput.disabled = false;
    }
    if (cpClueInput) cpClueInput.value = "";
    if (cpHintInput) cpHintInput.value = "";
    if (cpStoryInput) cpStoryInput.value = "";

    if (cpFormCard) {
      cpFormCard.hidden = false;
      cpNameInput.focus();
    }
  }

  function openEditCheckpoint(cp) {
    clearDraftMarker();
    hideFormAlert();

    const isLocked = currentGameStatus && currentGameStatus.game_state !== "setup";

    if (cpFormTitle) cpFormTitle.textContent = `Edit Checkpoint #${cp.position}`;
    if (cpIdInput) cpIdInput.value = cp.id;
    if (cpNameInput) cpNameInput.value = cp.name;
    if (cpLatInput) cpLatInput.value = cp.lat;
    if (cpLngInput) cpLngInput.value = cp.lng;
    if (cpRadiusInput) {
      cpRadiusInput.value = cp.radius;
      cpRadiusInput.disabled = isLocked;
    }
    if (cpPositionInput) {
      cpPositionInput.value = cp.position;
      cpPositionInput.disabled = isLocked;
    }
    if (cpClueInput) cpClueInput.value = cp.clue;
    if (cpHintInput) cpHintInput.value = cp.hint;
    if (cpStoryInput) cpStoryInput.value = cp.story || "";

    if (isLocked) {
      showFormAlert("Game has started. Location, radius, and order cannot be changed. Only clue, hint, and story may be edited.");
    }

    if (cpFormCard) {
      cpFormCard.hidden = false;
      (isLocked && cpClueInput ? cpClueInput : cpNameInput).focus();
    }

    if (mapInstance) {
      mapInstance.panTo([cp.lat, cp.lng], { animate: true });
    }
  }

  function closeCheckpointForm() {
    clearDraftMarker();
    hideFormAlert();
    if (cpRadiusInput) cpRadiusInput.disabled = false;
    if (cpPositionInput) cpPositionInput.disabled = false;
    if (cpFormCard) cpFormCard.hidden = true;
    if (cpIdInput) cpIdInput.value = "";
    if (cpForm) cpForm.reset();
  }

  async function handleCheckpointFormSubmit(event) {
    event.preventDefault();
    hideFormAlert();

    const id = cpIdInput ? cpIdInput.value : "";
    const name = cpNameInput ? cpNameInput.value.trim() : "";
    const lat = parseFloat(cpLatInput ? cpLatInput.value : "");
    const lng = parseFloat(cpLngInput ? cpLngInput.value : "");
    const radius = parseFloat(cpRadiusInput ? cpRadiusInput.value : 30);
    const positionVal = cpPositionInput && cpPositionInput.value ? parseInt(cpPositionInput.value, 10) : null;
    const clue = cpClueInput ? cpClueInput.value.trim() : "";
    const hint = cpHintInput ? cpHintInput.value.trim() : "";
    const story = cpStoryInput ? cpStoryInput.value.trim() : "";

    // Client-side validations
    if (!name) {
      showFormAlert("Please provide a checkpoint name.");
      return;
    }
    if (name.length > 60) {
      showFormAlert("Name must not exceed 60 characters.");
      return;
    }
    if (isNaN(lat) || isNaN(lng)) {
      showFormAlert("Coordinates are missing. Click on the map to set a location.");
      return;
    }
    if (isNaN(radius) || radius < 25 || radius > 100) {
      showFormAlert("Radius must be between 25 and 100 metres.");
      return;
    }
    if (!clue) {
      showFormAlert("Please enter a clue for players.");
      return;
    }
    if (clue.length > 300) {
      showFormAlert("Clue must not exceed 300 characters.");
      return;
    }
    if (!hint) {
      showFormAlert("Please enter an easier hint for players.");
      return;
    }
    if (hint.length > 300) {
      showFormAlert("Hint must not exceed 300 characters.");
      return;
    }
    if (story && story.length > 300) {
      showFormAlert("Story fact must not exceed 300 characters.");
      return;
    }

    const payload = {
      name,
      lat,
      lng,
      radius,
      position: positionVal,
      clue,
      hint,
      story: story || null,
    };

    if (cpFormSaveBtn) {
      cpFormSaveBtn.disabled = true;
      cpFormSaveBtn.textContent = "Saving...";
    }

    try {
      const isEdit = Boolean(id);
      const url = isEdit ? `/api/gods/checkpoints/${id}` : "/api/gods/checkpoints";
      const method = isEdit ? "PUT" : "POST";

      const res = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        const detailMsg = errorData.detail || "Failed to save checkpoint.";
        showFormAlert(typeof detailMsg === "string" ? detailMsg : JSON.stringify(detailMsg));
        return;
      }

      closeCheckpointForm();
      await Promise.all([
        loadCheckpoints(),
        loadGameStatus(),
      ]);
    } catch (err) {
      showFormAlert("Network error while saving checkpoint: " + err.message);
    } finally {
      if (cpFormSaveBtn) {
        cpFormSaveBtn.disabled = false;
        cpFormSaveBtn.textContent = "Save Checkpoint";
      }
    }
  }

  async function loadCheckpoints() {
    try {
      const res = await fetch("/api/gods/checkpoints", {
        headers: { "Accept": "application/json" },
      });

      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }

      checkpointsData = await res.json();
      renderCheckpoints();
    } catch (err) {
      showGlobalAlert("Failed to load checkpoints: " + err.message, true);
    }
  }

  function renderCheckpoints() {
    const minNeeded = (campusConfig && campusConfig.min_checkpoints) ? campusConfig.min_checkpoints : 5;
    const count = checkpointsData.length;
    const isLocked = Boolean(currentGameStatus && currentGameStatus.game_state !== "setup");

    // Update counter pill in Checkpoints tab
    if (counterPill) {
      counterPill.textContent = `${count} of ${minNeeded} needed`;
      if (count >= minNeeded) {
        counterPill.className = "counter-pill counter-satisfied";
      } else {
        counterPill.className = "counter-pill";
      }
    }

    // Also update checkpoint readiness counter in Game tab
    if (gameCpCounter) {
      gameCpCounter.textContent = `${count} of ${minNeeded} needed`;
      gameCpCounter.className = count >= minNeeded ? "counter-pill counter-satisfied" : "counter-pill";
    }
    if (gameCpStatusText) {
      if (count >= minNeeded) {
        gameCpStatusText.textContent = `Ready! You have ${count} checkpoints configured (minimum is ${minNeeded}).`;
      } else {
        gameCpStatusText.textContent = `Need ${minNeeded - count} more checkpoint(s) before game can start.`;
      }
    }

    // Update start button readiness if in setup state
    if (currentGameStatus && currentGameStatus.game_state === "setup" && btnGameStart) {
      if (count >= minNeeded) {
        btnGameStart.disabled = false;
        if (startDisabledReason) {
          startDisabledReason.textContent = "";
          startDisabledReason.hidden = true;
        }
      } else {
        btnGameStart.disabled = true;
        if (startDisabledReason) {
          startDisabledReason.textContent = `Cannot start: configure at least ${minNeeded} checkpoints (currently ${count}).`;
          startDisabledReason.hidden = false;
        }
      }
    }

    if (btnAddCheckpoint) {
      btnAddCheckpoint.disabled = isLocked;
      btnAddCheckpoint.title = isLocked ? "Cannot add checkpoints after game start" : "";
    }
    if (btnAddCheckpointList) {
      btnAddCheckpointList.disabled = isLocked;
      btnAddCheckpointList.title = isLocked ? "Cannot add checkpoints after game start" : "";
    }

    // Clear existing map markers and circles
    mapMarkers.forEach(({ marker, circle }) => {
      if (mapInstance) {
        mapInstance.removeLayer(marker);
        mapInstance.removeLayer(circle);
      }
    });
    mapMarkers.clear();

    // Render markers on map
    checkpointsData.forEach((cp) => {
      if (!mapInstance) return;

      const marker = L.marker([cp.lat, cp.lng], {
        draggable: !isLocked,
        title: `#${cp.position} ${cp.name}`,
      }).addTo(mapInstance);

      const circle = L.circle([cp.lat, cp.lng], {
        radius: cp.radius,
        color: "#188038",
        fillColor: "#188038",
        fillOpacity: 0.12,
        weight: 1.5,
      }).addTo(mapInstance);

      // On marker click: open form in edit mode
      marker.on("click", () => {
        openEditCheckpoint(cp);
      });

      // On marker drag: update coordinates in real time (only when not locked)
      if (!isLocked) {
        marker.on("drag", (evt) => {
          const pos = evt.target.getLatLng();
          const newLat = parseFloat(pos.lat.toFixed(6));
          const newLng = parseFloat(pos.lng.toFixed(6));
          circle.setLatLng(pos);

          // If the form is currently open for this checkpoint, update lat/lng inputs
          const currentOpenId = parseInt(cpIdInput ? cpIdInput.value : "", 10);
          if (currentOpenId === cp.id) {
            if (cpLatInput) cpLatInput.value = newLat;
            if (cpLngInput) cpLngInput.value = newLng;
          } else {
            // Open edit form so organizer can review & save new coordinates
            openEditCheckpoint({ ...cp, lat: newLat, lng: newLng });
          }
        });
      }

      mapMarkers.set(cp.id, { marker, circle });
    });

    // Render list
    if (!checkpointsList) return;
    checkpointsList.innerHTML = "";

    if (count === 0) {
      if (checkpointsEmpty) checkpointsEmpty.hidden = false;
      return;
    }

    if (checkpointsEmpty) checkpointsEmpty.hidden = true;

    checkpointsData.forEach((cp, index) => {
      const item = document.createElement("article");
      item.className = "gods-cp-item";
      item.setAttribute("role", "listitem");

      const isFirst = index === 0;
      const isLast = index === count - 1;

      item.innerHTML = `
        <div class="gods-cp-item-header">
          <span class="gods-cp-badge">#${cp.position}</span>
          <h3 class="gods-cp-name">${escapeHtml(cp.name)}</h3>
          <span class="gods-cp-meta">${cp.radius} m</span>
        </div>
        <p class="gods-cp-clue">${escapeHtml(cp.clue)}</p>
        <div class="gods-cp-actions">
          <button type="button" class="gods-btn-sm btn-edit" aria-label="Edit checkpoint ${escapeHtml(cp.name)}">
            Edit
          </button>
          <button type="button" class="gods-btn-sm btn-up" ${isFirst || isLocked ? "disabled" : ""} aria-label="Move checkpoint #${cp.position} up">
            &uarr; Up
          </button>
          <button type="button" class="gods-btn-sm btn-down" ${isLast || isLocked ? "disabled" : ""} aria-label="Move checkpoint #${cp.position} down">
            &darr; Down
          </button>
          <button type="button" class="gods-btn-sm gods-btn-danger btn-delete" ${isLocked ? "disabled" : ""} aria-label="Delete checkpoint ${escapeHtml(cp.name)}">
            Delete
          </button>
        </div>
      `;

      // Event listeners for list item buttons
      const editBtn = item.querySelector(".btn-edit");
      const upBtn = item.querySelector(".btn-up");
      const downBtn = item.querySelector(".btn-down");
      const delBtn = item.querySelector(".btn-delete");

      if (editBtn) {
        editBtn.addEventListener("click", () => openEditCheckpoint(cp));
      }

      if (upBtn && !isFirst && !isLocked) {
        upBtn.addEventListener("click", () => handleReorderCheckpoint(cp, cp.position - 1));
      }

      if (downBtn && !isLast && !isLocked) {
        downBtn.addEventListener("click", () => handleReorderCheckpoint(cp, cp.position + 1));
      }

      if (delBtn && !isLocked) {
        delBtn.addEventListener("click", () => handleDeleteCheckpoint(cp));
      }

      checkpointsList.appendChild(item);
    });
  }

  async function handleReorderCheckpoint(cp, newPosition) {
    if (currentGameStatus && currentGameStatus.game_state !== "setup") {
      showGlobalAlert("Checkpoint order cannot be changed once the game has started.", true);
      return;
    }
    hideGlobalAlert();
    try {
      const payload = {
        name: cp.name,
        lat: cp.lat,
        lng: cp.lng,
        radius: cp.radius,
        position: newPosition,
        clue: cp.clue,
        hint: cp.hint,
        story: cp.story,
      };

      const res = await fetch(`/api/gods/checkpoints/${cp.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to reorder checkpoint.");
      }

      await Promise.all([
        loadCheckpoints(),
        loadGameStatus(),
      ]);
    } catch (err) {
      showGlobalAlert("Reorder error: " + err.message, true);
    }
  }

  async function handleDeleteCheckpoint(cp) {
    if (currentGameStatus && currentGameStatus.game_state !== "setup") {
      showGlobalAlert("Checkpoints cannot be deleted once the game has started.", true);
      return;
    }
    const confirmed = window.confirm(`Delete checkpoint #${cp.position}: "${cp.name}"?`);
    if (!confirmed) return;

    hideGlobalAlert();
    try {
      const res = await fetch(`/api/gods/checkpoints/${cp.id}`, {
        method: "DELETE",
        headers: { "Accept": "application/json" },
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to delete checkpoint.");
      }

      // If the deleted checkpoint was open in the form, close it
      if (parseInt(cpIdInput ? cpIdInput.value : "", 10) === cp.id) {
        closeCheckpointForm();
      }

      await Promise.all([
        loadCheckpoints(),
        loadGameStatus(),
      ]);
    } catch (err) {
      showGlobalAlert("Delete error: " + err.message, true);
    }
  }

  // --- Admin Teams Tab Management ---

  async function loadAdminTeams() {
    try {
      const res = await fetch("/api/gods/teams", {
        headers: { "Accept": "application/json" },
      });
      if (res.status === 401) {
        showLoginForm();
        return;
      }
      if (!res.ok) {
        throw new Error("Failed to load registered teams.");
      }
      const data = await res.json();
      teamsData = data;
      renderAdminTeams(data);
    } catch (err) {
      showTeamsAlert("Teams fetch error: " + err.message, true);
    }
  }

  function renderAdminTeams(teams) {
    if (teamsCounterPill) {
      teamsCounterPill.textContent = `${teams.length} team${teams.length === 1 ? "" : "s"}`;
    }

    if (!teamsTableBody) return;

    if (!teams || teams.length === 0) {
      teamsTableBody.innerHTML = `
        <tr>
          <td colspan="8" class="table-empty-cell">No teams registered yet. Open registration and share the link.</td>
        </tr>
      `;
      return;
    }

    teamsTableBody.innerHTML = "";
    teams.forEach((t) => {
      const tr = document.createElement("tr");

      const isStale = (t.last_seen_s_ago !== null && t.last_seen_s_ago > 60);
      if (isStale) {
        tr.classList.add("team-row-stale");
      }

      // 1. Team Name
      const tdName = document.createElement("td");
      tdName.className = "team-name-cell";
      tdName.textContent = t.name;

      // 2. Team Code
      const tdCode = document.createElement("td");
      const codeBadge = document.createElement("span");
      codeBadge.className = "team-code-badge";
      codeBadge.textContent = t.code;
      tdCode.appendChild(codeBadge);

      // 3. Members
      const tdMembers = document.createElement("td");
      tdMembers.className = "team-members-cell";
      tdMembers.textContent = Array.isArray(t.members) ? t.members.join(", ") : "";

      // 4. Device status
      const tdDevice = document.createElement("td");
      const deviceBadge = document.createElement("span");
      const isBound = t.device_status === "bound";
      deviceBadge.className = `badge-device ${isBound ? "badge-device-bound" : "badge-device-free"}`;
      deviceBadge.textContent = isBound ? "Bound" : "Free";
      tdDevice.appendChild(deviceBadge);

      // 5. Last Seen
      const tdLastSeen = document.createElement("td");
      tdLastSeen.className = "team-last-seen-cell";
      if (t.last_seen_s_ago === null) {
        tdLastSeen.textContent = "Never";
      } else {
        tdLastSeen.textContent = `${t.last_seen_s_ago}s ago`;
      }
      if (isStale) {
        const staleChip = document.createElement("span");
        staleChip.className = "stale-warning-chip";
        staleChip.textContent = ">60s";
        staleChip.title = "Team inactive for more than 60 seconds";
        tdLastSeen.appendChild(staleChip);
      }

      // 6. Cleared count
      const tdCleared = document.createElement("td");
      tdCleared.textContent = `${t.cleared} / ${t.total}`;

      // 7. Adjusted Time
      const tdTime = document.createElement("td");
      tdTime.textContent = t.adjusted_time;

      // 8. Actions
      const tdActions = document.createElement("td");
      tdActions.className = "team-actions-cell";

      // Release Device button
      const btnRelease = document.createElement("button");
      btnRelease.type = "button";
      btnRelease.className = "gods-btn gods-btn-secondary gods-btn-sm";
      btnRelease.textContent = "Release Device";
      btnRelease.disabled = !isBound;
      if (!isBound) {
        btnRelease.title = "Device is already free (unbound)";
      }
      btnRelease.addEventListener("click", () => handleReleaseDevice(t));
      tdActions.appendChild(btnRelease);

      // Adjust Time button
      const btnAdjust = document.createElement("button");
      btnAdjust.type = "button";
      btnAdjust.className = "gods-btn gods-btn-secondary gods-btn-sm";
      btnAdjust.textContent = "Adjust Minutes";
      btnAdjust.addEventListener("click", () => openAdjustModal(t));
      tdActions.appendChild(btnAdjust);

      // Clear Checkpoint button
      const btnClearCp = document.createElement("button");
      btnClearCp.type = "button";
      btnClearCp.className = "gods-btn gods-btn-secondary gods-btn-sm";
      btnClearCp.textContent = "Clear Checkpoint";
      const isFinished = Boolean(t.finished || (t.total > 0 && t.cleared >= t.total));
      btnClearCp.disabled = isFinished;
      if (isFinished) {
        btnClearCp.title = "Team has already completed all checkpoints";
      }
      btnClearCp.addEventListener("click", () => openClearModal(t));
      tdActions.appendChild(btnClearCp);

      // Delete Team button
      const btnDelete = document.createElement("button");
      btnDelete.type = "button";
      btnDelete.className = "gods-btn gods-btn-danger gods-btn-sm";
      btnDelete.textContent = "Delete";
      btnDelete.addEventListener("click", () => openDeleteModal(t));
      tdActions.appendChild(btnDelete);

      tr.appendChild(tdName);
      tr.appendChild(tdCode);
      tr.appendChild(tdMembers);
      tr.appendChild(tdDevice);
      tr.appendChild(tdLastSeen);
      tr.appendChild(tdCleared);
      tr.appendChild(tdTime);
      tr.appendChild(tdActions);

      teamsTableBody.appendChild(tr);
    });
  }

  async function handleReleaseDevice(team) {
    hideTeamsAlert();
    try {
      const res = await fetch(`/api/gods/teams/${team.id}/release`, {
        method: "POST",
        headers: { "Accept": "application/json" },
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to release device.");
      }
      showTeamsAlert(`Device released for "${team.name}". The next phone entering team code will become the bound device.`, false);
      await loadAdminTeams();
    } catch (err) {
      showTeamsAlert("Release device error: " + err.message, true);
    }
  }

  function openAdjustModal(team) {
    if (!adjustModal) return;
    if (adjustModalAlert) adjustModalAlert.hidden = true;
    if (adjustTeamId) adjustTeamId.value = team.id;
    if (adjustTeamName) adjustTeamName.textContent = `Team: ${team.name} (${team.code})`;
    if (adjustMinutesInput) adjustMinutesInput.value = "";
    if (adjustReasonInput) adjustReasonInput.value = "";
    adjustModal.hidden = false;
    if (adjustMinutesInput) adjustMinutesInput.focus();
  }

  function closeAdjustModal() {
    if (!adjustModal) return;
    adjustModal.hidden = true;
    if (adjustForm) adjustForm.reset();
  }

  async function handleAdjustFormSubmit(e) {
    e.preventDefault();
    if (!adjustModalAlert || !adjustTeamId || !adjustMinutesInput || !adjustReasonInput) return;

    adjustModalAlert.hidden = true;
    const teamId = parseInt(adjustTeamId.value, 10);
    const minutes = parseInt(adjustMinutesInput.value, 10);
    const reason = adjustReasonInput.value.trim();

    if (isNaN(minutes) || minutes === 0) {
      adjustModalAlert.textContent = "Please enter non-zero minutes (positive for penalty, negative for bonus).";
      adjustModalAlert.hidden = false;
      return;
    }

    if (reason.length < 3 || reason.length > 120) {
      adjustModalAlert.textContent = "Reason is required (3 to 120 characters).";
      adjustModalAlert.hidden = false;
      return;
    }

    try {
      const res = await fetch(`/api/gods/teams/${teamId}/adjust`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({ minutes, reason }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to adjust team minutes.");
      }

      closeAdjustModal();
      showTeamsAlert(`Successfully adjusted ${minutes > 0 ? "+" : ""}${minutes} minutes for "${teamsData.find(t => t.id === teamId)?.name || 'team'}" (Reason: "${reason}").`, false);
      await loadAdminTeams();
    } catch (err) {
      adjustModalAlert.textContent = err.message;
      adjustModalAlert.hidden = false;
    }
  }

  function openDeleteModal(team) {
    if (!deleteModal) return;
    pendingDeleteTeamId = team.id;
    if (deleteModalAlert) deleteModalAlert.hidden = true;
    if (deleteModalWarning) {
      deleteModalWarning.textContent = `Permanently delete "${team.name}" (${team.code})? All cleared checkpoint progress and hint logs for this team will be deleted.`;
    }
    deleteModal.hidden = false;
  }

  function closeDeleteModal() {
    if (!deleteModal) return;
    deleteModal.hidden = true;
    pendingDeleteTeamId = null;
  }

  async function handleConfirmDelete() {
    if (!pendingDeleteTeamId) return;
    if (deleteModalAlert) deleteModalAlert.hidden = true;

    try {
      const res = await fetch(`/api/gods/teams/${pendingDeleteTeamId}`, {
        method: "DELETE",
        headers: { "Accept": "application/json" },
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to delete team.");
      }

      closeDeleteModal();
      showTeamsAlert("Team deleted successfully.", false);
      await loadAdminTeams();
    } catch (err) {
      if (deleteModalAlert) {
        deleteModalAlert.textContent = err.message;
        deleteModalAlert.hidden = false;
      }
    }
  }

  function openClearModal(team) {
    if (!clearModal) return;
    if (clearModalAlert) clearModalAlert.hidden = true;
    if (clearTeamId) clearTeamId.value = team.id;
    if (clearTeamName) clearTeamName.textContent = `Team: ${team.name} (${team.code})`;
    if (clearReasonInput) clearReasonInput.value = "";
    clearModal.hidden = false;
    if (clearReasonInput) clearReasonInput.focus();
  }

  function closeClearModal() {
    if (!clearModal) return;
    clearModal.hidden = true;
    if (clearForm) clearForm.reset();
  }

  async function handleClearFormSubmit(e) {
    e.preventDefault();
    if (!clearModalAlert || !clearTeamId || !clearReasonInput) return;

    clearModalAlert.hidden = true;
    const teamId = parseInt(clearTeamId.value, 10);
    const reason = clearReasonInput.value.trim();

    if (reason.length < 3 || reason.length > 120) {
      clearModalAlert.textContent = "Reason is required (3 to 120 characters).";
      clearModalAlert.hidden = false;
      return;
    }

    try {
      const res = await fetch(`/api/gods/teams/${teamId}/clear`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({ reason }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to force-clear checkpoint.");
      }

      closeClearModal();
      showTeamsAlert(`Successfully cleared checkpoint for "${teamsData.find(t => t.id === teamId)?.name || 'team'}" (Reason: "${reason}").`, false);
      await loadAdminTeams();
    } catch (err) {
      clearModalAlert.textContent = err.message;
      clearModalAlert.hidden = false;
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // --- Attach Tab & Action Event Listeners ---
  if (tabBtnGame) {
    tabBtnGame.addEventListener("click", () => switchTab("game"));
  }
  if (tabBtnCheckpoints) {
    tabBtnCheckpoints.addEventListener("click", () => switchTab("checkpoints"));
  }
  if (tabBtnTeams) {
    tabBtnTeams.addEventListener("click", () => switchTab("teams"));
  }
  if (btnRefreshTeams) {
    btnRefreshTeams.addEventListener("click", () => loadAdminTeams());
  }
  if (btnSwitchToCheckpoints) {
    btnSwitchToCheckpoints.addEventListener("click", () => switchTab("checkpoints"));
  }
  if (btnToggleRegistration) {
    btnToggleRegistration.addEventListener("click", handleToggleRegistration);
  }
  if (btnGameStart) {
    btnGameStart.addEventListener("click", handleStartGame);
  }
  if (btnGameEnd) {
    btnGameEnd.addEventListener("click", handleEndGame);
  }
  if (btnGameReset) {
    btnGameReset.addEventListener("click", handleResetGame);
  }

  // Modal event listeners
  if (adjustForm) {
    adjustForm.addEventListener("submit", handleAdjustFormSubmit);
  }
  if (btnAdjustCancel) {
    btnAdjustCancel.addEventListener("click", closeAdjustModal);
  }
  if (btnAdjustModalClose) {
    btnAdjustModalClose.addEventListener("click", closeAdjustModal);
  }
  if (adjustModal) {
    adjustModal.addEventListener("click", (e) => {
      if (e.target === adjustModal) closeAdjustModal();
    });
  }

  if (btnDeleteConfirm) {
    btnDeleteConfirm.addEventListener("click", handleConfirmDelete);
  }
  if (btnDeleteCancel) {
    btnDeleteCancel.addEventListener("click", closeDeleteModal);
  }
  if (btnDeleteModalClose) {
    btnDeleteModalClose.addEventListener("click", closeDeleteModal);
  }
  if (deleteModal) {
    deleteModal.addEventListener("click", (e) => {
      if (e.target === deleteModal) closeDeleteModal();
    });
  }

  if (clearForm) {
    clearForm.addEventListener("submit", handleClearFormSubmit);
  }
  if (btnClearCancel) {
    btnClearCancel.addEventListener("click", closeClearModal);
  }
  if (btnClearModalClose) {
    btnClearModalClose.addEventListener("click", closeClearModal);
  }
  if (clearModal) {
    clearModal.addEventListener("click", (e) => {
      if (e.target === clearModal) closeClearModal();
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (adjustModal && !adjustModal.hidden) closeAdjustModal();
      if (deleteModal && !deleteModal.hidden) closeDeleteModal();
      if (clearModal && !clearModal.hidden) closeClearModal();
    }
  });

  // Check session on page load
  checkSession();
});
