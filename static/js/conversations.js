/**
 * conversations.js — Sidebar conversation list management.
 */

// eslint-disable-next-line no-var
var Conversations = (function () {
  "use strict";

  /** @type {HTMLElement | null} */
  let listEl = null;

  /** @type {Array} */
  let conversations = [];

  function init() {
    listEl = document.getElementById("conversation-list");
  }

  /**
   * Fetch conversations from the backend and render the sidebar list.
   */
  async function refresh() {
    try {
      const token = await Auth.getAccessToken();
      const res = await fetch("/conversations?limit=30", {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        // Conversations endpoint may fail if Cosmos isn't configured — that's okay
        console.warn("Could not fetch conversations:", res.status);
        conversations = [];
        render();
        return;
      }

      const data = await res.json();
      conversations = data.conversations || [];
      render();
    } catch (err) {
      console.warn("Failed to load conversations:", err);
      conversations = [];
      render();
    }
  }

  /** Render the conversation list in the sidebar. */
  function render() {
    if (!listEl) return;
    listEl.innerHTML = "";

    if (conversations.length === 0) {
      listEl.innerHTML = `<div style="padding: 16px; text-align: center; color: var(--text-secondary); font-size: 13px;">No conversations yet</div>`;
      return;
    }

    const activeId = Chat.getCurrentConversationId();

    conversations.forEach((conv) => {
      const item = document.createElement("div");
      item.className = "conversation-item" + (conv.id === activeId ? " active" : "");
      item.dataset.id = conv.id;

      const title = document.createElement("div");
      title.className = "conv-title";
      title.textContent = conv.title || "Untitled";

      const preview = document.createElement("div");
      preview.className = "conv-preview";
      preview.textContent = conv.preview || "";

      const time = document.createElement("div");
      time.className = "conv-time";
      time.textContent = formatRelativeTime(conv.last_active_at);

      item.appendChild(title);
      if (conv.preview) item.appendChild(preview);
      item.appendChild(time);

      item.addEventListener("click", () => loadConversation(conv.id));

      listEl.appendChild(item);
    });
  }

  /**
   * Load a conversation's full history from the backend.
   * @param {string} conversationId
   */
  async function loadConversation(conversationId) {
    try {
      const token = await Auth.getAccessToken();
      const res = await fetch(`/conversations/${conversationId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        Chat.showError("Failed to load conversation");
        return;
      }

      const data = await res.json();
      const messages = (data.messages || []).map((m) => ({
        role: m.role,
        content: m.content,
        source_references: m.source_references || [],
        timestamp: m.timestamp,
      }));

      Chat.loadConversation(conversationId, messages);

      // Update active state in sidebar
      setActive(conversationId);

      // Close sidebar on mobile
      const sidebar = document.getElementById("sidebar");
      if (sidebar) sidebar.classList.remove("open");
    } catch (err) {
      console.error("Error loading conversation:", err);
      Chat.showError("Failed to load conversation");
    }
  }

  /**
   * Mark a conversation as active in the sidebar.
   * @param {string} conversationId
   */
  function setActive(conversationId) {
    if (!listEl) return;
    listEl.querySelectorAll(".conversation-item").forEach((el) => {
      el.classList.toggle("active", el.dataset.id === conversationId);
    });
  }

  /**
   * Called when a new message is sent (from chat.js) to refresh sidebar.
   * @param {string} conversationId
   * @param {string} messagePreview
   */
  function onNewMessage(conversationId, messagePreview) {
    // Optimistically update the sidebar — add or bump the conversation
    const existing = conversations.find((c) => c.id === conversationId);
    if (existing) {
      existing.preview = messagePreview.substring(0, 100);
      existing.last_active_at = new Date().toISOString();
      // Move to top
      conversations = [existing, ...conversations.filter((c) => c.id !== conversationId)];
    } else {
      conversations.unshift({
        id: conversationId,
        title: messagePreview.substring(0, 50),
        preview: messagePreview.substring(0, 100),
        last_active_at: new Date().toISOString(),
        status: "active",
      });
    }
    render();
    setActive(conversationId);

    // Refresh after a short delay to pick up the LLM-generated title
    setTimeout(() => refresh(), 3000);
  }

  /**
   * Format a timestamp as a relative time string.
   * @param {string} iso
   * @returns {string}
   */
  function formatRelativeTime(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      const now = new Date();
      const diffMs = now - d;
      const diffMin = Math.floor(diffMs / 60000);

      if (diffMin < 1) return "Just now";
      if (diffMin < 60) return `${diffMin}m ago`;
      const diffHrs = Math.floor(diffMin / 60);
      if (diffHrs < 24) return `${diffHrs}h ago`;
      const diffDays = Math.floor(diffHrs / 24);
      if (diffDays < 7) return `${diffDays}d ago`;
      return d.toLocaleDateString();
    } catch {
      return "";
    }
  }

  return {
    init,
    refresh,
    render,
    setActive,
    onNewMessage,
  };
})();
