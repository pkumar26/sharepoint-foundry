/**
 * chat.js — Chat message handling, rendering, and source citations.
 */

// eslint-disable-next-line no-var
var Chat = (function () {
  "use strict";

  /** Current conversation ID (null = new chat) */
  let currentConversationId = null;

  /** Reference to the messages container */
  let messagesEl = null;

  /** Reference to the typing indicator */
  let typingEl = null;

  function init() {
    messagesEl = document.getElementById("messages");
    typingEl = document.getElementById("typing-indicator");
  }

  /**
   * Send a message to the agent and render the response.
   * @param {string} text
   * @param {string | null} searchApproach
   */
  async function sendMessage(text, searchApproach) {
    // Remove welcome message if present
    const welcome = messagesEl.querySelector(".welcome-message");
    if (welcome) welcome.remove();

    // Render user message
    renderMessage({ role: "user", content: text, timestamp: new Date().toISOString() });

    // Show typing indicator
    typingEl.classList.remove("hidden");
    scrollToBottom();

    try {
      const token = await Auth.getAccessToken();
      const body = {
        message: text,
      };
      if (currentConversationId) {
        body.conversation_id = currentConversationId;
      }
      if (searchApproach) {
        body.search_approach = searchApproach;
      }

      const res = await fetch("/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.message || errorData.detail?.message || `Request failed (${res.status})`);
      }

      const data = await res.json();

      // Track conversation ID
      if (data.conversation_id) {
        currentConversationId = data.conversation_id;
      }

      // Render assistant response
      renderMessage({
        role: "assistant",
        content: data.message.content,
        source_references: data.message.source_references || [],
        timestamp: data.message.timestamp,
      });

      // Notify conversations module about the new message
      if (typeof Conversations !== "undefined" && Conversations.onNewMessage) {
        Conversations.onNewMessage(currentConversationId, text);
      }
    } catch (err) {
      console.error("Chat error:", err);
      showError(err.message || "Failed to send message. Please try again.");
    } finally {
      typingEl.classList.add("hidden");
      scrollToBottom();
    }
  }

  /**
   * Render a single message in the chat area.
   * @param {{ role: string, content: string, source_references?: Array, timestamp?: string }} msg
   */
  function renderMessage(msg) {
    const msgEl = document.createElement("div");
    msgEl.className = `message ${msg.role}`;

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    if (msg.role === "assistant") {
      // Render Markdown
      bubble.innerHTML = renderMarkdown(msg.content);
    } else {
      bubble.textContent = msg.content;
    }

    msgEl.appendChild(bubble);

    // Source references (assistant only)
    if (msg.role === "assistant" && msg.source_references && msg.source_references.length > 0) {
      msgEl.appendChild(renderSourceReferences(msg.source_references));
    }

    // Timestamp
    if (msg.timestamp) {
      const timeEl = document.createElement("div");
      timeEl.className = "message-time";
      timeEl.textContent = formatTime(msg.timestamp);
      msgEl.appendChild(timeEl);
    }

    messagesEl.appendChild(msgEl);
    scrollToBottom();
  }

  /**
   * Render Markdown content to HTML using marked.js.
   * @param {string} text
   * @returns {string}
   */
  function renderMarkdown(text) {
    if (typeof marked === "undefined") return escapeHtml(text);
    try {
      return marked.parse(text, { breaks: true });
    } catch {
      return escapeHtml(text);
    }
  }

  /**
   * Escape HTML for safe rendering.
   * @param {string} str
   * @returns {string}
   */
  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  /**
   * Render source reference citation cards.
   * @param {Array} refs
   * @returns {HTMLElement}
   */
  function renderSourceReferences(refs) {
    const container = document.createElement("div");
    container.className = "source-references";

    // Header (clickable to expand/collapse)
    const header = document.createElement("div");
    header.className = "source-references-header expanded";
    header.innerHTML = `
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="9 18 15 12 9 6"/>
      </svg>
      <span>Sources (${refs.length})</span>
    `;

    const cards = document.createElement("div");
    cards.className = "citation-cards";

    header.addEventListener("click", () => {
      header.classList.toggle("expanded");
      cards.classList.toggle("hidden");
    });

    refs.forEach((ref) => {
      const card = document.createElement("div");
      card.className = "citation-card";

      // Title (link if URL available)
      const title = document.createElement("a");
      title.className = "citation-title";
      title.textContent = ref.title || ref.document_url || "Untitled";
      if (ref.document_url) {
        title.href = ref.document_url;
        title.target = "_blank";
        title.rel = "noopener noreferrer";
      }

      // Snippet
      const snippet = document.createElement("div");
      snippet.className = "citation-snippet";
      snippet.textContent = ref.snippet || "";

      card.appendChild(title);
      if (ref.snippet) card.appendChild(snippet);

      // Relevance score bar
      if (ref.relevance_score != null) {
        const scoreEl = document.createElement("div");
        scoreEl.className = "citation-score";
        // Normalise score to 0–1 range (rerankerScore can be > 1)
        const normalisedScore = Math.min(ref.relevance_score / 4, 1);
        const pct = Math.round(normalisedScore * 100);
        scoreEl.innerHTML = `
          Relevance: ${ref.relevance_score.toFixed(2)}
          <span class="score-bar"><span class="score-fill" style="width:${pct}%"></span></span>
        `;
        card.appendChild(scoreEl);
      }

      cards.appendChild(card);
    });

    container.appendChild(header);
    container.appendChild(cards);
    return container;
  }

  /**
   * Format ISO timestamp for display.
   * @param {string} iso
   * @returns {string}
   */
  function formatTime(iso) {
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return "";
    }
  }

  /**
   * Show an error toast.
   * @param {string} message
   */
  function showError(message) {
    const toast = document.createElement("div");
    toast.className = "error-toast";
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
  }

  /** Auto-scroll to the bottom of the messages area. */
  function scrollToBottom() {
    requestAnimationFrame(() => {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    });
  }

  /** Clear the chat display and reset conversation state. */
  function clearChat() {
    currentConversationId = null;
    messagesEl.innerHTML = `
      <div class="welcome-message">
        <h2>Welcome to SharePoint Q&A</h2>
        <p>Ask questions about your SharePoint documents. I'll find relevant information and provide grounded answers with source citations.</p>
      </div>
    `;
  }

  /**
   * Load an existing conversation's messages into the chat area.
   * @param {string} conversationId
   * @param {Array} messages
   */
  function loadConversation(conversationId, messages) {
    currentConversationId = conversationId;
    messagesEl.innerHTML = "";
    messages.forEach((m) => renderMessage(m));
    scrollToBottom();
  }

  /** @returns {string | null} */
  function getCurrentConversationId() {
    return currentConversationId;
  }

  return {
    init,
    sendMessage,
    renderMessage,
    clearChat,
    loadConversation,
    getCurrentConversationId,
    showError,
  };
})();
