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

  // Elements: Game Tab
  const gameAlert = document.getElementById("gods-game-alert");
  const gameStateBadge = document.getElementById("game-state-badge");
  const gameCountdownBanner = document.getElementById("game-countdown-banner");
  const gameCountdownSec = document.getElementById("game-countdown-sec");
  const gameStateDesc = document.getElementById("game-state-desc");
  const btnGameStart = document.getElementById("btn-game-start");
  const btnGameEnd = document.getElementById("btn-game-end");
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

  // Elements: Teams Tab
  const teamsAlert = document.getElementById("gods-teams-alert");
  const teamsCountTotal = document.getElementById("teams-count-total");
  const teamsCountActive = document.getElementById("teams-count-active");
  const teamsCountFinished = document.getElementById("teams-count-finished");
  const btnRefreshTeams = document.getElementById("btn-refresh-teams");
  const teamsCardsList = document.getElementById("teams-cards-list");
  const teamsEmptyNotice = document.getElementById("teams-empty-notice");

  // Elements: Action Modals
  const forceClearModal = document.getElementById("force-clear-modal");
  const forceClearForm = document.getElementById("force-clear-form");
  const forceClearTeamId = document.getElementById("force-clear-team-id");
  const forceClearReason = document.getElementById("force-clear-reason");
  const forceClearAlert = document.getElementById("force-clear-alert");
  const btnCancelForceClear = document.getElementById("btn-cancel-force-clear");

  const adjustTimeModal = document.getElementById("adjust-time-modal");
  const adjustTimeForm = document.getElementById("adjust-time-form");
  const adjustTimeTeamId = document.getElementById("adjust-time-team-id");
  const adjustTimeMinutes = document.getElementById("adjust-time-minutes");
  const adjustTimeReason = document.getElementById("adjust-time-reason");
  const adjustTimeAlert = document.getElementById("adjust-time-alert");
  const btnCancelAdjustTime = document.getElementById("btn-cancel-adjust-time");

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

  function switchTab(tabName) {
    hideGameAlert();
    hideGlobalAlert();
    hideTeamsAlert();

    const isGame = tabName === "game";
    const isCp = tabName === "checkpoints";
    const isTeams = tabName === "teams";

    if (tabBtnGame) {
      tabBtnGame.classList.toggle("active", isGame);
      tabBtnGame.setAttribute("aria-selected", isGame ? "true" : "false");
    }
    if (tabBtnCheckpoints) {
      tabBtnCheckpoints.classList.toggle("active", isCp);
      tabBtnCheckpoints.setAttribute("aria-selected", isCp ? "true" : "false");
    }
    if (tabBtnTeams) {
      tabBtnTeams.classList.toggle("active", isTeams);
      tabBtnTeams.setAttribute("aria-selected", isTeams ? "true" : "false");
    }

    if (tabPanelGame) tabPanelGame.hidden = !isGame;
    if (tabPanelCheckpoints) tabPanelCheckpoints.hidden = !isCp;
    if (tabPanelTeams) tabPanelTeams.hidden = !isTeams;

    if (isCp && mapInstance) {
      setTimeout(() => mapInstance.invalidateSize(), 120);
    }
    if (isTeams) {
      loadTeams();
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
    const container = document.querySelector(".gods-container");
    if (container) container.classList.remove("gods-container-shell");
    if (adminShellSection) adminShellSection.hidden = true;
    if (loginSection) loginSection.hidden = false;
    if (passwordInput) passwordInput.value = "";
    hideGlobalAlert();
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
        loadTeams(),
      ]);
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
      await loadCheckpoints();
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

    // Update counter pill
    if (counterPill) {
      counterPill.textContent = `${count} of ${minNeeded} needed`;
      if (count >= minNeeded) {
        counterPill.className = "counter-pill counter-satisfied";
      } else {
        counterPill.className = "counter-pill";
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

      await loadCheckpoints();
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

      await loadCheckpoints();
    } catch (err) {
      showGlobalAlert("Delete error: " + err.message, true);
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

  // --- Teams Management Functions ---

  function formatRelativeTime(ts) {
    if (!ts) return "Never";
    const diffSec = Math.max(0, Math.floor((Date.now() - (ts * 1000)) / 1000));
    if (diffSec < 15) return "Just now";
    if (diffSec < 60) return `${diffSec}s ago`;
    const min = Math.floor(diffSec / 60);
    if (min < 60) return `${min}m ago`;
    const hrs = Math.floor(min / 60);
    return `${hrs}h ago`;
  }

  async function loadTeams() {
    hideTeamsAlert();
    try {
      const res = await fetch("/api/gods/teams", {
        headers: { "Accept": "application/json" },
      });
      if (!res.ok) {
        throw new Error("Failed to load teams");
      }
      const teams = await res.json();
      renderTeams(teams);
    } catch (err) {
      showTeamsAlert("Error loading teams: " + err.message, true);
    }
  }

  function renderTeams(teams) {
    if (!teamsCardsList) return;
    teamsCardsList.innerHTML = "";

    const total = teams.length;
    const active = teams.filter(t => t.device_bound).length;
    const finished = teams.filter(t => t.finished).length;

    if (teamsCountTotal) teamsCountTotal.textContent = `${total} team${total === 1 ? "" : "s"} registered`;
    if (teamsCountActive) teamsCountActive.textContent = `${active} active device${active === 1 ? "" : "s"}`;
    if (teamsCountFinished) teamsCountFinished.textContent = `${finished} finished`;

    if (teams.length === 0) {
      if (teamsEmptyNotice) teamsEmptyNotice.hidden = false;
      return;
    }
    if (teamsEmptyNotice) teamsEmptyNotice.hidden = true;

    teams.forEach(team => {
      const card = document.createElement("div");
      card.className = "gods-team-card";
      card.setAttribute("role", "listitem");

      const membersText = Array.isArray(team.members) ? team.members.join(", ") : String(team.members);
      const deviceBadgeClass = team.device_bound ? "badge-open" : "badge-setup";
      const deviceBadgeText = team.device_bound ? "Device Bound" : "No Device Bound";
      const nextCpText = team.finished
        ? "Completed all checkpoints"
        : (team.next_checkpoint ? `#${team.next_checkpoint.position} ${escapeHtml(team.next_checkpoint.name)}` : "None");

      card.innerHTML = `
        <div class="gods-team-header">
          <div class="gods-team-title-wrap">
            <h3 class="gods-team-name">${escapeHtml(team.name)}</h3>
            <span class="gods-team-code">Code: ${escapeHtml(team.code)}</span>
          </div>
          <span class="badge-status ${deviceBadgeClass}">${deviceBadgeText}</span>
        </div>

        <div class="gods-team-meta-row">
          <div class="gods-team-meta-item">
            <span class="gods-team-meta-label">Progress:</span>
            <span class="gods-team-meta-value"><strong>${team.cleared}</strong> / ${team.total} cleared</span>
          </div>
          <div class="gods-team-meta-item">
            <span class="gods-team-meta-label">Target:</span>
            <span class="gods-team-meta-value">${nextCpText}</span>
          </div>
          <div class="gods-team-meta-item">
            <span class="gods-team-meta-label">Adjusted Time:</span>
            <span class="gods-team-meta-value">${team.adjusted_time} ${team.penalty_s ? `(+${Math.round(team.penalty_s / 60)}m pen)` : ""}</span>
          </div>
          <div class="gods-team-meta-item">
            <span class="gods-team-meta-label">Last Seen:</span>
            <span class="gods-team-meta-value">${formatRelativeTime(team.last_seen)}</span>
          </div>
          <div class="gods-team-members">
            <strong>Members:</strong> ${escapeHtml(membersText)}
          </div>
        </div>

        <div class="gods-team-actions">
          <button type="button" class="gods-btn-sm btn-release-device" data-id="${team.id}" ${team.device_bound ? "" : "disabled"}>
            Release Device
          </button>
          <button type="button" class="gods-btn-sm btn-force-clear" data-id="${team.id}" data-name="${escapeHtml(team.name)}" ${team.finished ? "disabled" : ""}>
            Force Clear
          </button>
          <button type="button" class="gods-btn-sm btn-adjust-time" data-id="${team.id}" data-name="${escapeHtml(team.name)}">
            Adjust Time
          </button>
          <button type="button" class="gods-btn-sm gods-btn-danger btn-delete-team" data-id="${team.id}" data-name="${escapeHtml(team.name)}">
            Delete
          </button>
        </div>
      `;

      // Wire action buttons
      const btnRelease = card.querySelector(".btn-release-device");
      if (btnRelease && team.device_bound) {
        btnRelease.addEventListener("click", () => handleReleaseDevice(team));
      }

      const btnForce = card.querySelector(".btn-force-clear");
      if (btnForce && !team.finished) {
        btnForce.addEventListener("click", () => openForceClearModal(team));
      }

      const btnAdjust = card.querySelector(".btn-adjust-time");
      if (btnAdjust) {
        btnAdjust.addEventListener("click", () => openAdjustTimeModal(team));
      }

      const btnDel = card.querySelector(".btn-delete-team");
      if (btnDel) {
        btnDel.addEventListener("click", () => handleDeleteTeam(team));
      }

      teamsCardsList.appendChild(card);
    });
  }

  async function handleReleaseDevice(team) {
    const confirmed = window.confirm(`Release bound device for team "${team.name}" (${team.code})?\n\nThis will allow them to pair a replacement phone.`);
    if (!confirmed) return;
    hideTeamsAlert();

    try {
      const res = await fetch(`/api/gods/teams/${team.id}/release-device`, {
        method: "POST",
        headers: { "Accept": "application/json" },
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to release device.");
      }
      showTeamsAlert(`Device successfully released for team "${team.name}".`, false);
      await loadTeams();
    } catch (err) {
      showTeamsAlert("Release device error: " + err.message, true);
    }
  }

  function openForceClearModal(team) {
    if (!forceClearModal) return;
    if (forceClearTeamId) forceClearTeamId.value = team.id;
    if (forceClearReason) forceClearReason.value = "";
    if (forceClearAlert) {
      forceClearAlert.textContent = "";
      forceClearAlert.hidden = true;
    }
    const subtitle = document.getElementById("force-clear-subtitle");
    if (subtitle) {
      subtitle.textContent = `Advance team "${team.name}" past their current checkpoint without awarding power-ups.`;
    }
    forceClearModal.hidden = false;
  }

  function closeForceClearModal() {
    if (forceClearModal) forceClearModal.hidden = true;
  }

  async function handleForceClearSubmit(e) {
    e.preventDefault();
    const teamId = forceClearTeamId ? forceClearTeamId.value : "";
    const reason = forceClearReason ? forceClearReason.value.trim() : "";

    if (!reason) {
      if (forceClearAlert) {
        forceClearAlert.textContent = "Please provide an explanation for the audit log.";
        forceClearAlert.hidden = false;
      }
      return;
    }

    try {
      const res = await fetch(`/api/gods/teams/${teamId}/force-clear`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({ reason }),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to force clear checkpoint.");
      }
      closeForceClearModal();
      showTeamsAlert("Checkpoint force-cleared successfully.", false);
      await loadTeams();
    } catch (err) {
      if (forceClearAlert) {
        forceClearAlert.textContent = err.message;
        forceClearAlert.hidden = false;
      }
    }
  }

  function openAdjustTimeModal(team) {
    if (!adjustTimeModal) return;
    if (adjustTimeTeamId) adjustTimeTeamId.value = team.id;
    if (adjustTimeMinutes) adjustTimeMinutes.value = "";
    if (adjustTimeReason) adjustTimeReason.value = "";
    if (adjustTimeAlert) {
      adjustTimeAlert.textContent = "";
      adjustTimeAlert.hidden = true;
    }
    const subtitle = document.getElementById("adjust-time-subtitle");
    if (subtitle) {
      subtitle.textContent = `Adjust leaderboard time for team "${team.name}". Current adjusted: ${team.adjusted_time}`;
    }
    adjustTimeModal.hidden = false;
  }

  function closeAdjustTimeModal() {
    if (adjustTimeModal) adjustTimeModal.hidden = true;
  }

  async function handleAdjustTimeSubmit(e) {
    e.preventDefault();
    const teamId = adjustTimeTeamId ? adjustTimeTeamId.value : "";
    const minutes = parseInt(adjustTimeMinutes ? adjustTimeMinutes.value : "0", 10);
    const reason = adjustTimeReason ? adjustTimeReason.value.trim() : "";

    if (isNaN(minutes) || minutes === 0) {
      if (adjustTimeAlert) {
        adjustTimeAlert.textContent = "Please specify a non-zero number of minutes (e.g. +5 or -2).";
        adjustTimeAlert.hidden = false;
      }
      return;
    }
    if (!reason) {
      if (adjustTimeAlert) {
        adjustTimeAlert.textContent = "Please provide a reason for the audit log.";
        adjustTimeAlert.hidden = false;
      }
      return;
    }

    try {
      const res = await fetch(`/api/gods/teams/${teamId}/adjust-time`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({ minutes, reason }),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to adjust time.");
      }
      closeAdjustTimeModal();
      showTeamsAlert(`Time adjustment of ${minutes > 0 ? "+" : ""}${minutes}m applied successfully.`, false);
      await loadTeams();
    } catch (err) {
      if (adjustTimeAlert) {
        adjustTimeAlert.textContent = err.message;
        adjustTimeAlert.hidden = false;
      }
    }
  }

  async function handleDeleteTeam(team) {
    const confirmed = window.confirm(`Are you sure you want to delete team "${team.name}" (${team.code})?\n\nThis will remove all progress and cannot be undone.`);
    if (!confirmed) return;
    hideTeamsAlert();

    try {
      const res = await fetch(`/api/gods/teams/${team.id}`, {
        method: "DELETE",
        headers: { "Accept": "application/json" },
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to delete team.");
      }
      showTeamsAlert(`Team "${team.name}" deleted successfully.`, false);
      await loadTeams();
    } catch (err) {
      showTeamsAlert("Delete team error: " + err.message, true);
    }
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
    btnRefreshTeams.addEventListener("click", loadTeams);
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

  // Attach modal listeners
  if (forceClearForm) {
    forceClearForm.addEventListener("submit", handleForceClearSubmit);
  }
  if (btnCancelForceClear) {
    btnCancelForceClear.addEventListener("click", closeForceClearModal);
  }
  if (adjustTimeForm) {
    adjustTimeForm.addEventListener("submit", handleAdjustTimeSubmit);
  }
  if (btnCancelAdjustTime) {
    btnCancelAdjustTime.addEventListener("click", closeAdjustTimeModal);
  }

  // Check session on page load
  checkSession();
});
