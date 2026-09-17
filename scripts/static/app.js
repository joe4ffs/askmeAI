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
  let sessionId = null;

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

  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;

    const subject = document.getElementById("tutor-subject").value.trim();
    const fullMessage = subject ? `[Subject: ${subject}] ${message}` : message;

    appendMessage("user", message);
    chatInput.value = "";
    chatInput.focus();

    const pending = appendMessage("pending", "Thinking…");

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: fullMessage }),
      });
      const data = await res.json();
      pending.remove();
      if (!res.ok || data.error) {
        appendMessage("error", data.error || "Something went wrong.");
        return;
      }
      sessionId = data.session_id;
      appendMessage("assistant", data.reply);
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

    const summary = document.createElement("div");
    summary.className = "summary-card";
    summary.innerHTML = `
      <div class="summary-score">${escapeHtml(result.score_estimate)}</div>
      <div class="summary-text">${escapeHtml(result.overall_summary)}</div>
    `;
    gradeResults.appendChild(summary);

    result.questions.forEach((q, i) => {
      const card = document.createElement("div");
      card.className = `q-card ${q.is_correct ? "correct" : "incorrect"}`;
      card.innerHTML = `
        <div class="q-header">
          <div class="q-text">Q${i + 1}. ${escapeHtml(q.question_text)}</div>
          <span class="q-badge">${q.is_correct ? "Correct" : "Incorrect"}</span>
        </div>
        <div class="q-answer"><strong>Student wrote:</strong> ${escapeHtml(q.student_answer_as_written)}</div>
        <div class="q-explain">${escapeHtml(q.explanation)}</div>
        ${q.correction ? `<div class="q-correction"><strong>Correction:</strong> ${escapeHtml(q.correction)}</div>` : ""}
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

    const formData = new FormData();
    formData.append("file", selectedFile);

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
