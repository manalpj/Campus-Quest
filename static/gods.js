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
      await loadCheckpoints();
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
    if (cpRadiusInput) cpRadiusInput.value = defaultRadius;
    if (cpPositionInput) cpPositionInput.value = nextPosition;
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

    if (cpFormTitle) cpFormTitle.textContent = `Edit Checkpoint #${cp.position}`;
    if (cpIdInput) cpIdInput.value = cp.id;
    if (cpNameInput) cpNameInput.value = cp.name;
    if (cpLatInput) cpLatInput.value = cp.lat;
    if (cpLngInput) cpLngInput.value = cp.lng;
    if (cpRadiusInput) cpRadiusInput.value = cp.radius;
    if (cpPositionInput) cpPositionInput.value = cp.position;
    if (cpClueInput) cpClueInput.value = cp.clue;
    if (cpHintInput) cpHintInput.value = cp.hint;
    if (cpStoryInput) cpStoryInput.value = cp.story || "";

    if (cpFormCard) {
      cpFormCard.hidden = false;
      cpNameInput.focus();
    }

    if (mapInstance) {
      mapInstance.panTo([cp.lat, cp.lng], { animate: true });
    }
  }

  function closeCheckpointForm() {
    clearDraftMarker();
    hideFormAlert();
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

    // Update counter pill
    if (counterPill) {
      counterPill.textContent = `${count} of ${minNeeded} needed`;
      if (count >= minNeeded) {
        counterPill.className = "counter-pill counter-satisfied";
      } else {
        counterPill.className = "counter-pill";
      }
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
        draggable: true,
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

      // On marker drag: update coordinates in real time
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
          <button type="button" class="gods-btn-sm btn-up" ${isFirst ? "disabled" : ""} aria-label="Move checkpoint #${cp.position} up">
            &uarr; Up
          </button>
          <button type="button" class="gods-btn-sm btn-down" ${isLast ? "disabled" : ""} aria-label="Move checkpoint #${cp.position} down">
            &darr; Down
          </button>
          <button type="button" class="gods-btn-sm gods-btn-danger btn-delete" aria-label="Delete checkpoint ${escapeHtml(cp.name)}">
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

      if (upBtn && !isFirst) {
        upBtn.addEventListener("click", () => handleReorderCheckpoint(cp, cp.position - 1));
      }

      if (downBtn && !isLast) {
        downBtn.addEventListener("click", () => handleReorderCheckpoint(cp, cp.position + 1));
      }

      if (delBtn) {
        delBtn.addEventListener("click", () => handleDeleteCheckpoint(cp));
      }

      checkpointsList.appendChild(item);
    });
  }

  async function handleReorderCheckpoint(cp, newPosition) {
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

  // Check session on page load
  checkSession();
});
