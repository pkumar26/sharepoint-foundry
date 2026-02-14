/**
 * app.js — Main entry point. Initialises auth, wires up UI, manages state.
 */

(function () {
  "use strict";

  // ── Element references ────────────────────────────────────────
  const loginScreen = document.getElementById("login-screen");
  const appEl = document.getElementById("app");
  const loginBtn = document.getElementById("login-btn");
  const logoutBtn = document.getElementById("logout-btn");
  const userNameEl = document.getElementById("user-name");
  const newChatBtn = document.getElementById("new-chat-btn");
  const approachSelect = document.getElementById("approach-select");
  const messageInput = document.getElementById("message-input");
  const sendBtn = document.getElementById("send-btn");
  const sidebarToggle = document.getElementById("sidebar-toggle");
  const sidebar = document.getElementById("sidebar");
  const themeToggle = document.getElementById("theme-toggle");

  // ── Boot ──────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", boot);

  async function boot() {
    // Initialise modules
    Chat.init();
    Conversations.init();

    // Restore theme preference
    const savedTheme = localStorage.getItem("theme") || "light";
    document.documentElement.setAttribute("data-theme", savedTheme);

    try {
      await Auth.init();
    } catch (err) {
      console.error("MSAL init failed:", err);
      Chat.showError("Authentication initialisation failed. Please reload.");
      return;
    }

    // Check if already signed in
    const account = Auth.getAccount();
    if (account) {
      showApp(account);
    } else {
      showLogin();
    }

    // Wire up event listeners
    wireEvents();
  }

  // ── UI State ──────────────────────────────────────────────────

  function showLogin() {
    loginScreen.classList.remove("hidden");
    appEl.classList.add("hidden");
  }

  async function showApp(account) {
    loginScreen.classList.add("hidden");
    appEl.classList.remove("hidden");

    userNameEl.textContent = account.name || account.username || "";

    // Load available approaches
    await loadApproaches();

    // Load conversation history
    await Conversations.refresh();
  }

  // ── Approaches ────────────────────────────────────────────────

  async function loadApproaches() {
    try {
      const res = await fetch("/approaches");
      if (!res.ok) return;
      const data = await res.json();

      approachSelect.innerHTML = "";

      // Add "Server Default" option
      const defaultOpt = document.createElement("option");
      defaultOpt.value = "";
      defaultOpt.textContent = `Server Default (${data.default})`;
      approachSelect.appendChild(defaultOpt);

      // Add each available approach
      (data.approaches || []).forEach((approach) => {
        const opt = document.createElement("option");
        opt.value = approach;
        opt.textContent = formatApproachName(approach);
        approachSelect.appendChild(opt);
      });
    } catch (err) {
      console.warn("Could not load approaches:", err);
    }
  }

  /**
   * Format approach slug into a readable name.
   * @param {string} slug
   * @returns {string}
   */
  function formatApproachName(slug) {
    const names = {
      indexer: "Indexer (Direct Search)",
      foundryiq: "FoundryIQ (Remote KB)",
      indexed_sharepoint: "Indexed SharePoint (KB)",
    };
    return names[slug] || slug;
  }

  /** Get the currently selected approach (empty string = use server default). */
  function getSelectedApproach() {
    return approachSelect.value || null;
  }

  // ── Event Wiring ──────────────────────────────────────────────

  function wireEvents() {
    // Login
    loginBtn.addEventListener("click", async () => {
      try {
        loginBtn.disabled = true;
        loginBtn.textContent = "Signing in...";
        const account = await Auth.login();
        showApp(account);
      } catch (err) {
        console.error("Login error:", err);
        Chat.showError("Sign-in failed. Please try again.");
      } finally {
        loginBtn.disabled = false;
        loginBtn.textContent = "Sign in with Microsoft";
      }
    });

    // Logout
    logoutBtn.addEventListener("click", async () => {
      try {
        await Auth.logout();
      } catch {
        // Ignore logout errors
      }
      showLogin();
      Chat.clearChat();
    });

    // New chat
    newChatBtn.addEventListener("click", () => {
      Chat.clearChat();
      Conversations.setActive(null);
      messageInput.focus();
      // Close sidebar on mobile
      sidebar.classList.remove("open");
    });

    // Send message
    sendBtn.addEventListener("click", handleSend);

    // Enter to send (Shift+Enter for newline)
    messageInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    });

    // Enable/disable send button based on input
    messageInput.addEventListener("input", () => {
      sendBtn.disabled = !messageInput.value.trim();
      autoResizeTextarea();
    });

    // Sidebar toggle (mobile)
    sidebarToggle.addEventListener("click", () => {
      sidebar.classList.toggle("open");
    });

    // Close sidebar when clicking outside on mobile
    document.addEventListener("click", (e) => {
      if (
        sidebar.classList.contains("open") &&
        !sidebar.contains(e.target) &&
        e.target !== sidebarToggle &&
        !sidebarToggle.contains(e.target)
      ) {
        sidebar.classList.remove("open");
      }
    });

    // Theme toggle
    themeToggle.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme");
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("theme", next);
    });
  }

  // ── Send Handler ──────────────────────────────────────────────

  async function handleSend() {
    const text = messageInput.value.trim();
    if (!text) return;

    // Clear input and reset height
    messageInput.value = "";
    messageInput.style.height = "auto";
    sendBtn.disabled = true;

    const approach = getSelectedApproach();
    await Chat.sendMessage(text, approach);
  }

  // ── Textarea Auto-resize ──────────────────────────────────────

  function autoResizeTextarea() {
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + "px";
  }
})();
