(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const question = $("question");
  const messages = $("messages");
  const threads = new Map();
  const mobile = window.matchMedia("(max-width: 760px)");
  let activeId;
  let busy = false;
  let documentCount = 0;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const use = document.createElementNS(svg.namespaceURI, "use");
    svg.setAttribute("aria-hidden", "true");
    use.setAttribute("href", `#i-${name}`);
    svg.append(use);
    return svg;
  }

  // Render a small Markdown subset with text nodes. Model output never becomes HTML.
  function inline(node, text) {
    const pattern = /\*\*([^*\n]+)\*\*|`([^`\n]+)`/g;
    let offset = 0;
    for (const match of text.matchAll(pattern)) {
      node.append(document.createTextNode(text.slice(offset, match.index)));
      node.append(element(match[1] ? "strong" : "code", "", match[1] || match[2]));
      offset = match.index + match[0].length;
    }
    node.append(document.createTextNode(text.slice(offset)));
  }

  function formatAnswer(node, text) {
    let paragraph = [];
    let list = null;
    const flush = () => {
      if (paragraph.length) {
        const p = element("p");
        inline(p, paragraph.join(" "));
        node.append(p);
        paragraph = [];
      }
    };
    for (const line of text.split(/\r?\n/)) {
      const item = line.match(/^\s*(?:([-*])|\d+[.)])\s+(.+)$/);
      if (item) {
        flush();
        const tag = item[1] ? "ul" : "ol";
        if (!list || list.tagName.toLowerCase() !== tag) {
          list = element(tag);
          node.append(list);
        }
        const li = element("li");
        inline(li, item[2]);
        list.append(li);
      } else {
        list = null;
        if (!line.trim()) flush();
        else if (/^#{1,6}\s/.test(line)) {
          flush();
          const p = element("p");
          const strong = element("strong", "", line.replace(/^#{1,6}\s+/, ""));
          p.append(strong);
          node.append(p);
        } else paragraph.push(line.trim());
      }
    }
    flush();
  }

  function announce(text) { $("announcement").textContent = text; }

  function setMenu(open) {
    const visible = open && mobile.matches;
    document.body.classList.toggle("menu-open", visible);
    $("nav-overlay").hidden = !visible;
    $("menu-button").setAttribute("aria-expanded", String(visible));
    $("sidebar").inert = mobile.matches && !visible;
  }

  function composerState() {
    question.style.height = "auto";
    question.style.height = `${Math.min(150, Math.max(43, question.scrollHeight))}px`;
    $("send-button").disabled = busy || !question.value.trim();
    $("character-count").textContent = question.value.length > 3500
      ? `${question.value.length.toLocaleString()} / 4,000` : "";
  }

  function renderHistory() {
    $("conversation-list").replaceChildren();
    const populated = [...threads.values()].filter((thread) => thread.messages.length);
    $("history-note").hidden = populated.length > 0;
    for (const thread of populated.reverse()) {
      const button = element("button", `conversation-button${thread.id === activeId ? " active" : ""}`);
      button.type = "button";
      button.disabled = busy;
      button.title = thread.title;
      if (thread.id === activeId) button.setAttribute("aria-current", "true");
      button.append(icon("chat"), element("span", "", thread.title));
      button.addEventListener("click", () => {
        activeId = thread.id;
        render();
        setMenu(false);
        question.focus();
      });
      $("conversation-list").append(button);
    }
  }

  function showReferences(sources) {
    $("reference-title").textContent = "Behind this answer.";
    const body = $("reference-body");
    body.replaceChildren(element("p", "dialog-description", "These company documents supplied the passages retrieved for this answer."));
    const list = element("ul", "reference-list");
    for (const source of sources) {
      const li = element("li");
      const info = element("div");
      info.append(element("strong", "", source.name));
      info.append(element("small", "", `${source.passages} retrieved passage${source.passages === 1 ? "" : "s"}`));
      li.append(icon("book"), info);
      list.append(li);
    }
    body.append(list);
    $("reference-dialog").showModal();
  }

  function renderMessage(message) {
    const article = element("article", `message ${message.role}${message.error ? " error-message" : ""}`);
    if (message.role === "user") {
      article.append(element("div", "user-bubble", message.text));
      return article;
    }
    const heading = element("div", "assistant-heading");
    heading.append(element("span", "assistant-mark", "1"), element("span", "", "1 Finance assistant"));
    article.append(heading);
    const body = element("div", "assistant-text");
    if (message.pending) {
      const pending = element("div", "pending");
      const dots = element("span", "typing-dots");
      dots.setAttribute("aria-hidden", "true");
      dots.append(element("span"), element("span"), element("span"));
      pending.append(dots, element("span", "", "Finding clarity in your company knowledge…"));
      body.append(pending);
    } else if (message.error) {
      body.append(element("p", "", message.text));
      const retry = element("button", "retry-button", "Try again");
      retry.type = "button";
      retry.disabled = busy;
      retry.addEventListener("click", () => submitQuestion(message.question, message));
      body.append(retry);
    } else {
      formatAnswer(body, message.text);
    }
    article.append(body);
    if (!message.pending && !message.error) {
      const footer = element("div", "message-footer");
      if (message.sources.length) {
        const button = element("button", "sources-button");
        button.type = "button";
        button.append(icon("book"), element("span", "", `${message.sources.length} source${message.sources.length === 1 ? "" : "s"}`));
        button.addEventListener("click", () => showReferences(message.sources));
        footer.append(button);
      }
      const copy = element("button", "icon-button copy-button");
      copy.type = "button";
      copy.setAttribute("aria-label", "Copy answer");
      copy.title = "Copy answer";
      copy.append(icon("copy"));
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(message.text);
          copy.replaceChildren(icon("check"));
          announce("Answer copied.");
          setTimeout(() => copy.replaceChildren(icon("copy")), 2000);
        } catch { announce("Copy is unavailable in this browser. Select the answer text to copy it."); }
      });
      footer.append(copy);
      if (Number.isFinite(message.elapsed_ms)) {
        footer.append(element("span", "message-time", `${(message.elapsed_ms / 1000).toFixed(1)}s`));
      }
      article.append(footer);
    }
    return article;
  }

  function render() {
    const thread = threads.get(activeId);
    $("welcome").hidden = thread.messages.length > 0;
    messages.hidden = thread.messages.length === 0;
    messages.replaceChildren(...thread.messages.map(renderMessage));
    $("conversation-title").textContent = thread.messages.length ? thread.title : "";
    question.disabled = busy;
    $("new-chat").disabled = busy;
    document.querySelectorAll("[data-question]").forEach((button) => { button.disabled = busy; });
    renderHistory();
    composerState();
    requestAnimationFrame(() => { $("content").scrollTop = $("content").scrollHeight; });
  }

  function newConversation() {
    if (busy) return;
    const empty = [...threads.values()].find((thread) => !thread.messages.length);
    activeId = empty ? empty.id : crypto.randomUUID();
    if (!empty) threads.set(activeId, { id: activeId, title: "New conversation", messages: [] });
    question.value = "";
    render();
    setMenu(false);
  }

  async function submitQuestion(text, retryMessage = null) {
    const trimmed = text.trim();
    if (busy || !trimmed || trimmed.length > 4000) return;
    const thread = threads.get(activeId);
    if (!retryMessage) {
      if (!thread.messages.length) thread.title = trimmed.length > 45 ? `${trimmed.slice(0, 45)}…` : trimmed;
      thread.messages.push({ role: "user", text: trimmed });
    }
    const reply = retryMessage || { role: "assistant" };
    Object.assign(reply, { pending: true, error: false, question: trimmed });
    if (!retryMessage) thread.messages.push(reply);
    busy = true;
    question.value = "";
    setMenu(false);
    render();
    announce("Finding an answer. The first question may take a little longer while the models load.");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 180000);
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmed }),
        signal: controller.signal,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "The assistant is unavailable. Please try again.");
      if (typeof payload.answer !== "string" || !Array.isArray(payload.sources)) throw new Error("An answer could not be loaded. Please try again.");
      Object.assign(reply, {
        pending: false,
        text: payload.answer,
        sources: payload.sources.filter((source) => typeof source.name === "string" && Number.isInteger(source.passages)),
        elapsed_ms: payload.elapsed_ms,
      });
      $("connection").classList.remove("offline");
      $("connection-label").textContent = "Company knowledge";
      announce("Answer ready.");
    } catch (error) {
      const text = error.name === "AbortError"
        ? "This answer is taking longer than expected. Please try again."
        : error instanceof TypeError || error instanceof SyntaxError
          ? "Could not reach the assistant. Check that the chatbot server is running, then try again."
          : error.message;
      Object.assign(reply, { pending: false, error: true, text });
      announce(text);
    } finally {
      clearTimeout(timer);
      busy = false;
      render();
      question.focus();
    }
  }

  async function health() {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch("/api/health", { signal: controller.signal });
      const payload = await response.json();
      if (!response.ok || payload.status !== "ok") throw new Error("Unavailable");
      documentCount = payload.documents;
      $("document-count").textContent = `${documentCount} company documents`;
      $("connection").classList.remove("offline");
      $("connection-label").textContent = "Company knowledge";
    } catch {
      $("connection").classList.add("offline");
      $("connection-label").textContent = "Connection unavailable";
    } finally { clearTimeout(timer); }
  }

  $("chat-form").addEventListener("submit", (event) => { event.preventDefault(); submitQuestion(question.value); });
  question.addEventListener("input", composerState);
  question.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      submitQuestion(question.value);
    }
  });
  document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => submitQuestion(button.dataset.question));
  });
  $("new-chat").addEventListener("click", () => { newConversation(); question.focus(); });
  $("menu-button").addEventListener("click", () => setMenu(!document.body.classList.contains("menu-open")));
  $("nav-close").addEventListener("click", () => { setMenu(false); $("menu-button").focus(); });
  $("nav-overlay").addEventListener("click", () => setMenu(false));
  mobile.addEventListener("change", () => setMenu(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setMenu(false);
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      question.focus();
    }
  });
  $("knowledge-info").addEventListener("click", () => {
    $("reference-title").textContent = "Your company knowledge.";
    const body = $("reference-body");
    body.replaceChildren(element("p", "dialog-description", `Ask questions based on ${documentCount || "the available"} company documents: MoneySign assessments and profiles, 1 Finance services, financial basics, and product FAQs.`));
    body.append(element("p", "dialog-description", "Conversations stay in this tab and clear when you refresh. Each question is answered independently using the existing company knowledge pipeline."));
    $("reference-dialog").showModal();
  });
  $("close-dialog").addEventListener("click", () => $("reference-dialog").close());
  $("reference-dialog").addEventListener("click", (event) => {
    if (event.target !== $("reference-dialog")) return;
    const bounds = event.target.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) event.target.close();
  });

  newConversation();
  health();
  setInterval(health, 30000);
})();
