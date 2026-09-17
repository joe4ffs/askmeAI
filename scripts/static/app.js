(() => {
  "use strict";

  // ---- Mode switching ----
  const modeButtons = document.querySelectorAll(".mode-btn");
  const panels = { tutor: document.getElementById("panel-tutor"), grade: document.getElementById("panel-grade") };

  modeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      modeButtons.forEach((b) => { b.classList.remove("active"); b.setAttribute("aria-selected", "false"); });
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      Object.values(panels).forEach((p) => p.classList.remove("active"));
      panels[btn.dataset.mode].classList.add("active");
    });
  });

  // ---- Subject suggestions ----
  fetch("/api/subjects")
    .then((r) => r.json())
    .then(({ subjects }) => {
      const lists = [document.getElementById("subject-list"), document.getElementById("subject-list-2")];
      lists.forEach((list) => {
        subjects.forEach((s) => {
          const opt = document.createElement("option");
          opt.value = s;
          list.appendChild(opt);
        });
      });
    })
    .catch(() => {});

  // ---- Tutor chat ----
  const chatLog = document.getElementById("chat-log");
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const sessionListEl = document.getElementById("session-list");
  const newChatBtn = document.getElementById("new-chat-btn");
  const thinkingToggle = document.getElementById("thinking-toggle");
  let sessionId = localStorage.getItem("ai-grader-session-id") || null;

  try {
    const saved = localStorage.getItem("ai-grader-thinking");
    if (saved !== null) thinkingToggle.checked = saved === "true";
  } catch (err) {}
  thinkingToggle.addEventListener("change", () => {
    try {
      localStorage.setItem("ai-grader-thinking", thinkingToggle.checked);
    } catch (err) {}
  });

  const WELCOME_HTML =
    "Hi — ask me anything academic: math, science, history, writing, code, whatever you're stuck on.";

  function setSessionId(id) {
    sessionId = id;
    if (id) localStorage.setItem("ai-grader-session-id", id);
    else localStorage.removeItem("ai-grader-session-id");
  }

  function appendMessage(role, text) {
    const wrap = document.createElement("div");
    wrap.className = `chat-msg ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    bubble.textContent = text;
    wrap.appendChild(bubble);
    chatLog.appendChild(wrap);
    chatLog.scrollTop = chatLog.scrollHeight;
    return wrap;
  }

  // Types `text` into a fresh assistant bubble a few characters at a time. Chunked (not
  // char-by-char) so long replies don't take forever, and scrolls along as it grows.
  function typewriteMessage(text, { charsPerTick = 3, intervalMs = 12 } = {}) {
    const wrap = document.createElement("div");
    wrap.className = "chat-msg assistant";
    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    wrap.appendChild(bubble);
    chatLog.appendChild(wrap);

    return new Promise((resolve) => {
      let i = 0;
      const timer = setInterval(() => {
        i = Math.min(text.length, i + charsPerTick);
        bubble.textContent = text.slice(0, i);
        chatLog.scrollTop = chatLog.scrollHeight;
        if (i >= text.length) {
          clearInterval(timer);
          resolve(wrap);
        }
      }, intervalMs);
    });
  }

  function clearChatLog() {
    chatLog.innerHTML = "";
  }

  async function loadSessionList() {
    try {
      const res = await fetch("/api/sessions");
      const { sessions } = await res.json();
      sessionListEl.innerHTML = "";
      if (!sessions.length) {
        const li = document.createElement("li");
        li.className = "session-empty";
        li.textContent = "No saved chats yet.";
        sessionListEl.appendChild(li);
        return;
      }
      sessions.forEach((s) => {
        const li = document.createElement("li");
        li.className = "session-item" + (s.id === sessionId ? " active" : "");
        const title = document.createElement("span");
        title.className = "session-title";
        title.textContent = s.title;
        const del = document.createElement("button");
        del.className = "session-delete";
        del.textContent = "×";
        del.title = "Delete this chat";
        del.addEventListener("click", async (e) => {
          e.stopPropagation();
          await fetch(`/api/sessions/${s.id}`, { method: "DELETE" });
          if (s.id === sessionId) startNewChat();
          loadSessionList();
        });
        li.appendChild(title);
        li.appendChild(del);
        li.addEventListener("click", () => resumeSession(s.id));
        sessionListEl.appendChild(li);
      });
    } catch (err) {
      sessionListEl.innerHTML = "";
    }
  }

  async function resumeSession(id) {
    setSessionId(id);
    clearChatLog();
    try {
      const res = await fetch(`/api/sessions/${id}`);
      const data = await res.json();
      if (data.messages && data.messages.length) {
        data.messages.forEach((m) => appendMessage(m.role, m.content));
      } else {
        appendMessage("assistant", WELCOME_HTML);
      }
    } catch (err) {
      appendMessage("error", `Could not load chat: ${err.message}`);
    }
    loadSessionList();
  }

  function startNewChat() {
    setSessionId(null);
    clearChatLog();
    appendMessage("assistant", WELCOME_HTML);
    loadSessionList();
  }

  newChatBtn.addEventListener("click", startNewChat);

  // Restore last session on page load, or show the welcome message fresh.
  if (sessionId) {
    resumeSession(sessionId);
  } else {
    loadSessionList();
  }

  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;

    const subject = document.getElementById("tutor-subject").value.trim();

    appendMessage("user", message);
    chatInput.value = "";
    chatInput.focus();

    const pending = appendMessage("pending", "Thinking…");

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message, subject, thinking: thinkingToggle.checked }),
      });
      const data = await res.json();
      pending.remove();
      if (!res.ok || data.error) {
        appendMessage("error", data.error || "Something went wrong.");
        return;
      }
      const isNewSession = sessionId !== data.session_id;
      setSessionId(data.session_id);
      await typewriteMessage(data.reply);
      if (isNewSession) loadSessionList();
    } catch (err) {
      pending.remove();
      appendMessage("error", `Connection error: ${err.message}`);
    }
  });

  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatForm.requestSubmit();
    }
  });

  // ---- Script grading ----
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const filePreview = document.getElementById("file-preview");
  const fileNameEl = document.getElementById("file-name");
  const fileClearBtn = document.getElementById("file-clear");
  const gradeBtn = document.getElementById("grade-btn");
  const gradeStatus = document.getElementById("grade-status");
  const gradeEmpty = document.getElementById("grade-empty");
  const gradeResults = document.getElementById("grade-results");

  let selectedFile = null;

  function setFile(file) {
    selectedFile = file;
    if (file) {
      fileNameEl.textContent = `${file.name} (${(file.size / 1024).toFixed(0)} KB)`;
      filePreview.classList.remove("hidden");
      dropzone.classList.add("has-file");
      gradeBtn.disabled = false;
    } else {
      filePreview.classList.add("hidden");
      dropzone.classList.remove("has-file");
      gradeBtn.disabled = true;
      fileInput.value = "";
    }
  }

  dropzone.addEventListener("click", (e) => {
    if (e.target !== fileClearBtn) fileInput.click();
  });
  fileInput.addEventListener("change", () => setFile(fileInput.files[0] || null));

  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.add("dragover"); })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.remove("dragover"); })
  );
  dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) setFile(file);
  });

  fileClearBtn.addEventListener("click", (e) => { e.stopPropagation(); setFile(null); });

  function setStatus(text, kind) {
    gradeStatus.textContent = text;
    gradeStatus.className = `status-line ${kind || ""}`;
  }

  function renderResult(result) {
    gradeEmpty.classList.add("hidden");
    gradeResults.classList.remove("hidden");
    gradeResults.innerHTML = "";

    const flaggedCount = result.questions.filter((q) => q.needs_human_review).length;

    const summary = document.createElement("div");
    summary.className = "summary-card";
    summary.innerHTML = `
      <div class="summary-score">${escapeHtml(result.score_estimate)}</div>
      <div class="summary-text">${escapeHtml(result.overall_summary)}</div>
      ${
        flaggedCount > 0
          ? `<div class="summary-flag">⚠ ${flaggedCount} of ${result.questions.length} question${flaggedCount === 1 ? "" : "s"} flagged for human review</div>`
          : `<div class="summary-flag ok">✓ All questions graded with high confidence</div>`
      }
    `;
    gradeResults.appendChild(summary);

    result.questions.forEach((q, i) => {
      const card = document.createElement("div");
      card.className = `q-card ${q.is_correct ? "correct" : "incorrect"} ${q.needs_human_review ? "flagged" : ""}`;
      card.innerHTML = `
        <div class="q-header">
          <div class="q-text">Q${i + 1}. ${escapeHtml(q.question_text)}</div>
          <div class="q-badges">
            ${q.needs_human_review ? `<span class="q-badge review">Needs Review</span>` : ""}
            <span class="q-badge confidence-${escapeHtml(q.confidence)}">${escapeHtml(q.confidence)} confidence</span>
            <span class="q-badge">${q.is_correct ? "Correct" : "Incorrect"}</span>
          </div>
        </div>
        <div class="q-concept">${escapeHtml(q.concept)}</div>
        <div class="q-answer"><strong>Student wrote:</strong> ${escapeHtml(q.student_answer_as_written)}</div>
        <div class="q-explain">${escapeHtml(q.explanation)}</div>
        ${q.correction ? `<div class="q-correction"><strong>Correction:</strong> ${escapeHtml(q.correction)}</div>` : ""}
        ${q.needs_human_review ? `<div class="q-review-reason"><strong>Why flagged:</strong> ${escapeHtml(q.review_reason)}</div>` : ""}
      `;
      gradeResults.appendChild(card);
    });
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str ?? "";
    return div.innerHTML;
  }

  gradeBtn.addEventListener("click", async () => {
    if (!selectedFile) return;
    gradeBtn.disabled = true;
    setStatus("Grading — this can take a bit for a real model…");

    const subject = document.getElementById("grade-subject").value.trim();
    const formData = new FormData();
    formData.append("file", selectedFile);
    if (subject) formData.append("subject", subject);

    try {
      const res = await fetch("/api/grade-script", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok || data.error) {
        setStatus(data.error || "Grading failed.", "error");
        gradeBtn.disabled = false;
        return;
      }
      setStatus("Done.", "ok");
      renderResult(data.result);
    } catch (err) {
      setStatus(`Connection error: ${err.message}`, "error");
    } finally {
      gradeBtn.disabled = false;
    }
  });
})();
