/**
 * Campus Quest - Admin Panel Frontend Logic (/gods)
 *
 * Communicates with /api/gods endpoints using signed HttpOnly session cookies.
 * Does not store any credentials or session state in localStorage/sessionStorage.
 */

document.addEventListener("DOMContentLoaded", () => {
  const loginSection = document.getElementById("login-section");
  const adminShellSection = document.getElementById("admin-shell-section");
  const loginForm = document.getElementById("login-form");
  const usernameInput = document.getElementById("admin-username-input");
  const passwordInput = document.getElementById("admin-password-input");
  const loginBtn = document.getElementById("login-submit-btn");
  const logoutBtn = document.getElementById("logout-btn");
  const loginAlert = document.getElementById("login-alert");
  const currentAdminName = document.getElementById("current-admin-name");

  function showAlert(message, isError = true) {
    if (!loginAlert) return;
    loginAlert.textContent = message;
    loginAlert.hidden = false;
    loginAlert.className = isError ? "gods-alert gods-alert-error" : "gods-alert gods-alert-success";
  }

  function hideAlert() {
    if (!loginAlert) return;
    loginAlert.textContent = "";
    loginAlert.hidden = true;
  }

  function showAdminShell(username) {
    if (currentAdminName) {
      currentAdminName.textContent = username;
    }
    if (loginSection) loginSection.hidden = true;
    if (adminShellSection) adminShellSection.hidden = false;
    hideAlert();
  }

  function showLoginForm() {
    if (adminShellSection) adminShellSection.hidden = true;
    if (loginSection) loginSection.hidden = false;
    if (passwordInput) passwordInput.value = "";
  }

  // Check current session on page load
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
      // Network error or server unreachable
      showLoginForm();
      showAlert("Could not connect to server. Check your network.", true);
    }
  }

  // Handle Login submission
  if (loginForm) {
    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      hideAlert();

      const username = usernameInput ? usernameInput.value.trim() : "";
      const password = passwordInput ? passwordInput.value : "";

      if (!username || !password) {
        showAlert("Please enter both User ID and password.", true);
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
          showAlert("Invalid User ID or password.", true);
        } else if (response.status === 429) {
          showAlert("Too many failed attempts. Please wait a minute before retrying.", true);
        } else {
          showAlert("Server error during login. Please try again later.", true);
        }
      } catch (err) {
        showAlert("Network error. Unable to reach server.", true);
      } finally {
        if (loginBtn) {
          loginBtn.disabled = false;
          loginBtn.textContent = "Log In";
        }
      }
    });
  }

  // Handle Logout action
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
          showAlert("Logout failed on server, resetting local view.", true);
          showLoginForm();
        }
      } catch (err) {
        showAlert("Network error during logout.", true);
        showLoginForm();
      } finally {
        logoutBtn.disabled = false;
      }
    });
  }

  // Initialize view state
  checkSession();
});
