/**
 * UR_PICASSO - Lógica Frontend (Client-side)
 * ==========================================
 * Gerencia a experiência do convidado no celular/PC:
 * - Contagem regressiva para pose
 * - Upload e visualização vetorial instantânea
 * - Comunicação via WebSocket para progresso ao vivo
 * - Funções de calibração do operador
 */

document.addEventListener("DOMContentLoaded", () => {
  // ── ELEMENTOS DO DOM ──────────────────────────────────────────────────
  const views = {
    capture: document.getElementById("step-capture"),
    preview: document.getElementById("step-preview"),
    drawing: document.getElementById("step-drawing"),
    completed: document.getElementById("step-completed")
  };

  const tabCamera = document.getElementById("tab-camera");
  const tabUpload = document.getElementById("tab-upload");
  const cameraPanel = document.getElementById("camera-panel");
  const uploadPanel = document.getElementById("upload-panel");

  const btnSnap = document.getElementById("btn-snap");
  const countdownOverlay = document.getElementById("countdown-overlay");
  const countdownNumber = document.getElementById("countdown-number");
  const fileInput = document.getElementById("file-input");
  const dropzone = document.getElementById("dropzone");

  const svgContainer = document.getElementById("svg-container");
  const drawingSvgLive = document.getElementById("drawing-svg-live");
  const statStrokes = document.getElementById("stat-strokes");
  const statTime = document.getElementById("stat-time");
  const profileBtns = document.querySelectorAll(".profile-btn");

  const btnBackCapture = document.getElementById("btn-back-capture");
  const btnStartDrawing = document.getElementById("btn-start-drawing");
  const btnAbortDrawing = document.getElementById("btn-abort-drawing");
  const btnNewPortrait = document.getElementById("btn-new-portrait");
  const btnDownloadSvg = document.getElementById("btn-download-svg");
  const btnDownloadImg = document.getElementById("btn-download-img");

  let lastProcessedSvg = "";
  let lastProcessedBase64 = "";

  const progressBarFill = document.getElementById("progress-bar-fill");
  const progressPercentLabel = document.getElementById("progress-percent-label");
  const progressStatusText = document.getElementById("progress-status-text");

  const robotStatusBadge = document.getElementById("robot-status-badge");
  const robotStatusText = document.getElementById("robot-status-text");

  // Modal do Operador
  const btnOperatorModal = document.getElementById("btn-operator-modal");
  const operatorModal = document.getElementById("operator-modal");
  const btnCloseModal = document.getElementById("btn-close-modal");
  const btnCalibTouch = document.getElementById("btn-calib-touch");
  const btnCalibOrigin = document.getElementById("btn-calib-origin");
  const btnMoveHome = document.getElementById("btn-move-home");

  let currentProfile = "ultra_fast";
  let ws = null;

  // ── NAVEGAÇÃO ENTRE ETAPAS ────────────────────────────────────────────
  function showView(viewKey) {
    Object.keys(views).forEach(key => {
      if (key === viewKey) {
        views[key].classList.remove("hidden");
        views[key].classList.add("active");
      } else {
        views[key].classList.add("hidden");
        views[key].classList.remove("active");
      }
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // Alternância entre Câmera e Upload
  tabCamera.addEventListener("click", () => {
    tabCamera.classList.add("active");
    tabUpload.classList.remove("active");
    cameraPanel.classList.remove("hidden");
    uploadPanel.classList.add("hidden");
  });

  tabUpload.addEventListener("click", () => {
    tabUpload.classList.add("active");
    tabCamera.classList.remove("active");
    uploadPanel.classList.remove("hidden");
    cameraPanel.classList.add("hidden");
  });

  // ── CAPTURA COM CONTAGEM REGRESSIVA (3..2..1.. 📸) ───────────────────
  btnSnap.addEventListener("click", () => {
    btnSnap.disabled = true;
    countdownOverlay.classList.remove("hidden");
    let count = 3;
    countdownNumber.textContent = count;

    const timer = setInterval(() => {
      count--;
      if (count > 0) {
        countdownNumber.textContent = count;
      } else {
        clearInterval(timer);
        countdownNumber.textContent = "📸";
        setTimeout(() => {
          countdownOverlay.classList.add("hidden");
          executeCapture();
          btnSnap.disabled = false;
        }, 500);
      }
    }, 900);
  });

  async function executeCapture() {
    btnSnap.textContent = "Processando traços...";
    try {
      const formData = new FormData();
      formData.append("profile", currentProfile);

      const res = await fetch("/api/capture", {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      if (data.success) {
        renderPreviewData(data);
        showView("preview");
      } else {
        alert("Erro na captura: " + (data.error || "Tente novamente"));
      }
    } catch (e) {
      alert("Falha de comunicação com o servidor.");
    } finally {
      btnSnap.innerHTML = '<span class="btn-icon-inside">📸</span> Tirar Foto Agora';
    }
  }

  // ── UPLOAD DE FOTO DO CELULAR ─────────────────────────────────────────
  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      uploadFile(e.target.files[0]);
    }
  });

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.style.borderColor = "var(--accent-cyan)";
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.style.borderColor = "var(--border-color)";
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.style.borderColor = "var(--border-color)";
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });

  async function uploadFile(file) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("profile", currentProfile);

    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      if (data.success) {
        renderPreviewData(data);
        showView("preview");
      } else {
        alert("Erro no upload: " + (data.error || "Formato inválido"));
      }
    } catch (e) {
      alert("Falha ao enviar arquivo.");
    }
  }

  // ── RENDERIZAÇÃO DA PRÉ-VISUALIZAÇÃO ──────────────────────────────────
  function renderPreviewData(data) {
    lastProcessedSvg = data.svg;
    lastProcessedBase64 = data.preview_image_base64;
    svgContainer.innerHTML = data.svg;
    drawingSvgLive.innerHTML = data.svg;
    statStrokes.textContent = data.stroke_count;
    statTime.textContent = data.estimated_time_s + " s";
  }

  // Alternância de Perfil (Ultra Rápido vs Equilibrado)
  profileBtns.forEach(btn => {
    btn.addEventListener("click", async () => {
      profileBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentProfile = btn.getAttribute("data-profile");

      // Reprocessa com novo perfil
      try {
        const formData = new FormData();
        formData.append("profile", currentProfile);
        const res = await fetch("/api/reprocess", {
          method: "POST",
          body: formData
        });
        const data = await res.json();
        if (data.success) {
          renderPreviewData(data);
        }
      } catch (e) {
        console.error("Erro ao reprocessar:", e);
      }
    });
  });

  btnBackCapture.addEventListener("click", () => {
    showView("capture");
  });

  // ── INÍCIO DO DESENHO NO ROBÔ ─────────────────────────────────────────
  btnStartDrawing.addEventListener("click", async () => {
    btnStartDrawing.disabled = true;
    try {
      const res = await fetch("/api/draw", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        showView("drawing");
        updateProgressBar(0, "Iniciando robô UR3...");
      } else {
        alert(data.error || "Falha ao iniciar o robô.");
      }
    } catch (e) {
      alert("Erro ao conectar com o robô.");
    } finally {
      btnStartDrawing.disabled = false;
    }
  });

  // Cancelar / Abortar
  btnAbortDrawing.addEventListener("click", async () => {
    if (confirm("Tem certeza que deseja interromper o desenho do robô?")) {
      try {
        await fetch("/api/abort", { method: "POST" });
        showView("preview");
      } catch (e) {
        alert("Erro ao enviar aborto.");
      }
    }
  });

  btnNewPortrait.addEventListener("click", () => {
    showView("capture");
  });

  // Download do SVG Vetorial
  btnDownloadSvg.addEventListener("click", () => {
    if (!lastProcessedSvg) return;
    const blob = new Blob([lastProcessedSvg], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "meu_retrato_ur_picasso.svg";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });

  // Download da Imagem JPG
  btnDownloadImg.addEventListener("click", () => {
    if (!lastProcessedBase64) return;
    const a = document.createElement("a");
    a.href = "data:image/jpeg;base64," + lastProcessedBase64;
    a.download = "meu_retrato_ur_picasso.jpg";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });

  // ── ATUALIZAÇÃO DA BARRA DE PROGRESSO ─────────────────────────────────
  function updateProgressBar(percent, text) {
    progressBarFill.style.width = `${percent}%`;
    progressPercentLabel.textContent = `${Math.round(percent)}%`;
    if (text) progressStatusText.textContent = text;
  }

  // ── WEBSOCKET PARA FEEDBACK EM TEMPO REAL ─────────────────────────────
  function initWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/progress`;

    ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.event === "progress") {
          updateProgressBar(msg.progress, msg.message);
          if (msg.progress >= 100) {
            setTimeout(() => {
              showView("completed");
            }, 1200);
          }
        } else if (msg.event === "aborted") {
          updateProgressBar(0, "Cancelado.");
          showView("preview");
        } else if (msg.event === "initial_state") {
          if (msg.status === "drawing") {
            showView("drawing");
            updateProgressBar(msg.progress, msg.message);
          }
        }
      } catch (e) {
        console.error("Erro WebSocket:", e);
      }
    };

    ws.onclose = () => {
      setTimeout(initWebSocket, 2500); // Reconexão automática
    };
  }

  initWebSocket();

  // ── POLLING DE STATUS DO ROBÔ ─────────────────────────────────────────
  async function checkRobotStatus() {
    try {
      const res = await fetch("/api/status");
      const status = await res.json();

      if (status.robot_connected) {
        robotStatusBadge.className = "badge badge-online";
        robotStatusText.textContent = "UR3 Online";
      } else {
        robotStatusBadge.className = "badge badge-sim";
        robotStatusText.textContent = "Modo Simulado";
      }
    } catch (e) {
      robotStatusBadge.className = "badge badge-offline";
      robotStatusText.textContent = "Offline";
    }
  }

  checkRobotStatus();
  setInterval(checkRobotStatus, 5000);

  // ── MODAL DO OPERADOR & CALIBRAÇÃO ────────────────────────────────────
  btnOperatorModal.addEventListener("click", () => {
    operatorModal.classList.remove("hidden");
  });

  btnCloseModal.addEventListener("click", () => {
    operatorModal.classList.add("hidden");
  });

  document.querySelector(".modal-backdrop").addEventListener("click", () => {
    operatorModal.classList.add("hidden");
  });

  btnCalibTouch.addEventListener("click", async () => {
    btnCalibTouch.disabled = true;
    btnCalibTouch.textContent = "Executando traço de teste...";
    try {
      const res = await fetch("/api/calibrate/touch", { method: "POST" });
      const data = await res.json();
      alert(data.message || "Teste concluído!");
    } catch (e) {
      alert("Falha no teste.");
    } finally {
      btnCalibTouch.disabled = false;
      btnCalibTouch.textContent = "✏️ Testar Toque da Caneta (8mm)";
    }
  });

  btnCalibOrigin.addEventListener("click", async () => {
    if (confirm("Deseja salvar a posição atual da ponta da caneta como a origem do papel A6?")) {
      try {
        const res = await fetch("/api/calibrate/origin", { method: "POST" });
        const data = await res.json();
        alert(data.message || "Origem calibrada!");
      } catch (e) {
        alert("Erro ao calibrar origem.");
      }
    }
  });

  btnMoveHome.addEventListener("click", async () => {
    try {
      btnMoveHome.disabled = true;
      const res = await fetch("/api/home", { method: "POST" });
      const data = await res.json();
      alert(data.message);
    } catch (e) {
      alert("Erro ao mover para HOME.");
    } finally {
      btnMoveHome.disabled = false;
    }
  });
});

