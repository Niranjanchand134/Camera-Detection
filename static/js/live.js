/**
 * Crimson Vision - Interactive Live Monitoring Controller
 * Direct Camera Tap-to-Focus, Smooth Zoom & Pan System,
 * Automatic In-Browser Audio on Focus, and Video/Audio Recording Controls
 */

let viewMode = "grid";         // "grid" | "single"
let activeCamera = null;
let zoomLevel = 1.0;
let panX = 0;
let panY = 0;
let isDragging = false;
let startX = 0;
let startY = 0;
let hasDragged = false;
let isAudioActive = false;
let cameraAudioCaps = {};

document.addEventListener("DOMContentLoaded", () => {
  setupInteractiveStream();
  setupZoomButtons();
  setupAIModeButtons();
  setupRecordingButton();
  setupAudioPlayer();
  setupKeyboardControls();

  // Start telemetry polling
  pollStatus();
  setInterval(pollStatus, 1500);
});

function setupInteractiveStream() {
  const viewport = document.getElementById("stream-viewport");
  const streamImg = document.getElementById("live-video-stream");
  if (!viewport || !streamImg) return;

  // 1. Direct Tap on Camera Tile (Grid View -> Single View; Single View -> Return)
  viewport.addEventListener("click", (e) => {
    if (hasDragged) {
      hasDragged = false;
      return;
    }

    if (viewMode === "grid") {
      const rect = streamImg.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;
      const relX = clickX / rect.width;
      const relY = clickY / rect.height;

      const names = (typeof CAMERA_NAMES !== "undefined" && CAMERA_NAMES.length)
        ? CAMERA_NAMES
        : ["Camera 1", "Camera 2", "Camera 3", "Camera 4"];
      const n = names.length;
      const cols = Math.ceil(Math.sqrt(n));
      const rows = Math.ceil(n / cols);

      const col = Math.floor(relX * cols);
      const row = Math.floor(relY * rows);
      const index = row * cols + col;

      if (index >= 0 && index < n) {
        enterSingleCamera(names[index]);
      }
    } else {
      if (zoomLevel <= 1.05) {
        returnToGrid();
      }
    }
  });

  viewport.addEventListener("dblclick", () => {
    if (viewMode === "single") {
      returnToGrid();
    }
  });

  // 2. Mouse Wheel Zoom in Single View
  viewport.addEventListener("wheel", (e) => {
    if (viewMode === "single") {
      e.preventDefault();
      if (e.deltaY < 0) {
        setZoom(zoomLevel + 0.25);
      } else {
        setZoom(zoomLevel - 0.25);
      }
    }
  }, { passive: false });

  // 3. Mouse Drag to Pan
  viewport.addEventListener("mousedown", (e) => {
    if (viewMode === "single" && zoomLevel > 1.0) {
      isDragging = true;
      hasDragged = false;
      startX = e.clientX - panX;
      startY = e.clientY - panY;
      viewport.style.cursor = "grabbing";
    }
  });

  window.addEventListener("mousemove", (e) => {
    if (isDragging && viewMode === "single") {
      const newX = e.clientX - startX;
      const newY = e.clientY - startY;
      if (Math.abs(newX - panX) > 3 || Math.abs(newY - panY) > 3) {
        hasDragged = true;
      }
      panX = newX;
      panY = newY;
      applyTransform();
    }
  });

  window.addEventListener("mouseup", () => {
    if (isDragging) {
      isDragging = false;
      if (viewport) {
        viewport.style.cursor = zoomLevel > 1.0 ? "grab" : "pointer";
      }
    }
  });
}

function enterSingleCamera(camName) {
  viewMode = "single";
  activeCamera = camName;
  resetZoom();

  const streamImg = document.getElementById("live-video-stream");
  const feedLabel = document.getElementById("feed-name-label");
  const viewBadge = document.getElementById("view-mode-badge");
  const zoomBar = document.getElementById("zoom-control-bar");
  const returnBtn = document.getElementById("btn-return-grid");
  const hintEl = document.getElementById("stream-gesture-hint");

  streamImg.src = `/video_feed/${encodeURIComponent(camName)}`;
  feedLabel.textContent = `Focused Feed: ${camName}`;
  viewBadge.textContent = `Focused: ${camName}`;
  viewBadge.style.color = "var(--accent-primary)";

  returnBtn.style.display = "inline-flex";
  zoomBar.style.display = "inline-flex";

  if (hintEl) {
    hintEl.innerHTML = `<span>🔍 Scroll wheel or +/- to zoom • Drag / WASD to pan • Click or ESC for Grid</span>`;
    hintEl.classList.add("fade-out");
  }

  highlightActiveCamPill(camName);

  // Auto-play audio when focusing any camera
  startBrowserAudio(camName);
}

function returnToGrid() {
  viewMode = "grid";
  activeCamera = null;
  resetZoom();

  const streamImg = document.getElementById("live-video-stream");
  const feedLabel = document.getElementById("feed-name-label");
  const viewBadge = document.getElementById("view-mode-badge");
  const zoomBar = document.getElementById("zoom-control-bar");
  const returnBtn = document.getElementById("btn-return-grid");
  const hintEl = document.getElementById("stream-gesture-hint");

  streamImg.src = "/video_feed/grid";
  feedLabel.textContent = "Multi-Camera Grid View";
  viewBadge.textContent = "Grid View (Tap Camera to Zoom)";
  viewBadge.style.color = "var(--text-secondary)";

  returnBtn.style.display = "none";
  zoomBar.style.display = "none";

  if (hintEl) {
    hintEl.innerHTML = `<span>👆 Tap any camera to focus & zoom • Scroll to zoom in/out • Drag to pan</span>`;
    hintEl.classList.remove("fade-out");
  }

  highlightActiveCamPill(null);

  // Auto-stop audio when returning to grid
  stopBrowserAudio();
}

function setupZoomButtons() {
  document.getElementById("btn-zoom-in")?.addEventListener("click", (e) => {
    e.stopPropagation();
    setZoom(zoomLevel + 0.3);
  });
  document.getElementById("btn-zoom-out")?.addEventListener("click", (e) => {
    e.stopPropagation();
    setZoom(zoomLevel - 0.3);
  });
  document.getElementById("btn-zoom-reset")?.addEventListener("click", (e) => {
    e.stopPropagation();
    resetZoom();
  });
}

function setZoom(val) {
  zoomLevel = Math.max(1.0, Math.min(4.0, val));
  if (zoomLevel === 1.0) {
    panX = 0;
    panY = 0;
  }
  const zoomText = document.getElementById("zoom-level-display");
  if (zoomText) zoomText.textContent = `${zoomLevel.toFixed(1)}x`;
  applyTransform();

  const viewport = document.getElementById("stream-viewport");
  if (viewport) {
    viewport.style.cursor = zoomLevel > 1.0 ? "grab" : "pointer";
  }
}

function resetZoom() {
  zoomLevel = 1.0;
  panX = 0;
  panY = 0;
  const zoomText = document.getElementById("zoom-level-display");
  if (zoomText) zoomText.textContent = "1.0x";
  applyTransform();

  const viewport = document.getElementById("stream-viewport");
  if (viewport) {
    viewport.style.cursor = "pointer";
  }
}

function applyTransform() {
  const streamImg = document.getElementById("live-video-stream");
  if (!streamImg) return;

  const maxPan = (zoomLevel - 1.0) * 350;
  panX = Math.max(-maxPan, Math.min(maxPan, panX));
  panY = Math.max(-maxPan, Math.min(maxPan, panY));

  streamImg.style.transform = `scale(${zoomLevel}) translate(${panX / zoomLevel}px, ${panY / zoomLevel}px)`;
}

function setupKeyboardControls() {
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (viewMode === "single") returnToGrid();
    } else if (e.key === "+" || e.key === "=") {
      if (viewMode === "single") setZoom(zoomLevel + 0.25);
    } else if (e.key === "-") {
      if (viewMode === "single") setZoom(zoomLevel - 0.25);
    } else if (viewMode === "single" && zoomLevel > 1.0) {
      const step = 40;
      if (e.key === "ArrowLeft" || e.key.toLowerCase() === "a") {
        panX += step; applyTransform();
      } else if (e.key === "ArrowRight" || e.key.toLowerCase() === "d") {
        panX -= step; applyTransform();
      } else if (e.key === "ArrowUp" || e.key.toLowerCase() === "w") {
        panY += step; applyTransform();
      } else if (e.key === "ArrowDown" || e.key.toLowerCase() === "s") {
        panY -= step; applyTransform();
      }
    } else if (e.key.toLowerCase() === "m") {
      document.getElementById("btn-audio-toggle")?.click();
    } else if (e.key.toLowerCase() === "r") {
      document.getElementById("btn-record-toggle")?.click();
    }
  });
}

function highlightActiveCamPill(camName) {
  document.querySelectorAll(".cam-status-pill").forEach((pill) => {
    if (camName && pill.id === `pill-${camName.replace(/ /g, "-")}`) {
      pill.classList.add("active");
    } else {
      pill.classList.remove("active");
    }
  });
}

function setupAIModeButtons() {
  const modeButtons = document.querySelectorAll("#ai-mode-group .btn-pill");
  modeButtons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const cat = btn.getAttribute("data-cat");

      try {
        const res = await fetch("/api/control/detection", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category: cat })
        });
        await res.json();

        modeButtons.forEach((b) => b.classList.remove("active", "crimson", "emerald"));
        if (cat === "off") {
          btn.classList.add("active");
        } else if (cat === "person") {
          btn.classList.add("active", "emerald");
        } else if (cat === "vehicle") {
          btn.classList.add("active", "crimson");
        }

        const tagEl = document.getElementById("active-category-tag");
        if (tagEl) {
          tagEl.textContent = cat;
        }
      } catch (err) {
        console.error("Failed to change AI detection mode:", err);
      }
    });
  });
}

// ---------------- RECORDING TOGGLE BUTTON ----------------
function setupRecordingButton() {
  const recBtn = document.getElementById("btn-record-toggle");
  if (!recBtn) return;

  recBtn.addEventListener("click", async () => {
    try {
      const target = viewMode === "single" && activeCamera ? activeCamera : "all";
      const res = await fetch("/api/control/recording", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "toggle", camera: target })
      });
      const data = await res.json();
      pollStatus();
    } catch (err) {
      console.error("Recording toggle error:", err);
    }
  });
}

// ---------------- LIVE IN-BROWSER AUDIO STREAMING ----------------
function setupAudioPlayer() {
  const audioBtn = document.getElementById("btn-audio-toggle");
  const audioPlayer = document.getElementById("live-audio-player");

  if (!audioBtn || !audioPlayer) return;

  audioBtn.addEventListener("click", () => {
    if (isAudioActive) {
      stopBrowserAudio();
    } else {
      const targetCam = activeCamera || (CAMERA_NAMES && CAMERA_NAMES.length ? CAMERA_NAMES[0] : "Camera 1");
      startBrowserAudio(targetCam);
    }
  });

  audioPlayer.addEventListener("error", (e) => {
    console.warn("Audio playback error:", e);
    const audioBtnText = document.getElementById("audio-btn-text");
    if (audioBtnText) audioBtnText.textContent = "Audio: N/A";
  });
}

function startBrowserAudio(camName) {
  const audioPlayer = document.getElementById("live-audio-player");
  if (!audioPlayer) return;

  // Check if camera has audio capability
  if (cameraAudioCaps[camName] === false) {
    const audioBtnText = document.getElementById("audio-btn-text");
    if (audioBtnText) audioBtnText.textContent = `No Mic (${camName})`;
    isAudioActive = false;
    audioPlayer.pause();
    audioPlayer.src = "";
    updateAudioButtonUI(camName);
    return;
  }

  isAudioActive = true;
  audioPlayer.src = `/audio_feed/${encodeURIComponent(camName)}?t=${Date.now()}`;
  audioPlayer.play().catch((err) => {
    console.debug("Browser audio autoplay blocked or interrupted:", err);
  });

  updateAudioButtonUI(camName);
}

function stopBrowserAudio() {
  const audioPlayer = document.getElementById("live-audio-player");
  if (audioPlayer) {
    audioPlayer.pause();
    audioPlayer.src = "";
  }
  isAudioActive = false;
  updateAudioButtonUI();
}

function updateAudioButtonUI(camName = null) {
  const audioBtnText = document.getElementById("audio-btn-text");
  const audioBtn = document.getElementById("btn-audio-toggle");
  if (!audioBtnText || !audioBtn) return;

  const target = camName || activeCamera;

  if (isAudioActive && target) {
    audioBtn.classList.add("active");
    audioBtnText.textContent = `Audio: Live (${target})`;
  } else if (target && cameraAudioCaps[target] === false) {
    audioBtn.classList.remove("active");
    audioBtnText.textContent = `No Mic (${target})`;
  } else {
    audioBtn.classList.remove("active");
    audioBtnText.textContent = target ? `Audio: Off (${target})` : "Audio: Off";
  }
}

// ---------------- TELEMETRY POLLING ----------------
async function pollStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();

    // Cache audio capabilities
    if (data.audio_capabilities) {
      cameraAudioCaps = data.audio_capabilities;
    }

    // Update Camera status dots
    let onlineCount = 0;
    if (data.cameras) {
      for (const [camName, info] of Object.entries(data.cameras)) {
        const dotId = "dot-" + camName.replace(/ /g, "-");
        const dot = document.getElementById(dotId);
        if (dot) {
          if (info.status === "online") {
            dot.classList.remove("offline");
            onlineCount++;
          } else {
            dot.classList.add("offline");
          }
        }
      }
    }

    const counterEl = document.getElementById("online-counter");
    if (counterEl) {
      counterEl.textContent = `${onlineCount} / ${data.total_cameras} Online`;
    }

    // Update Record Button UI State
    const recBtn = document.getElementById("btn-record-toggle");
    const recText = document.getElementById("record-btn-text");
    const rec = data.recording;

    if (rec && rec.recording) {
      recBtn?.classList.add("recording");
      const mins = Math.floor(rec.duration_seconds / 60).toString().padStart(2, "0");
      const secs = (rec.duration_seconds % 60).toString().padStart(2, "0");
      const camCount = rec.active_targets ? rec.active_targets.length : 0;
      if (recText) {
        recText.textContent = `Stop Rec (${mins}:${secs} - ${camCount} Cams)`;
      }
    } else {
      recBtn?.classList.remove("recording");
      if (recText) {
        recText.textContent = "Start Recording";
      }
    }

    // Update Live Telemetry list
    updateTelemetryList(data.detections, data.active_category);

  } catch (err) {
    console.debug("Status polling error:", err);
  }
}

function updateTelemetryList(detectionsMap, activeCategory) {
  const container = document.getElementById("live-detections-container");
  if (!container) return;

  if (!activeCategory || activeCategory === "off" || !detectionsMap) {
    container.innerHTML = `<div style="color: var(--text-muted); font-size: 0.82rem; text-align: center; padding: 1.5rem 0;">AI Detection is currently Off.</div>`;
    return;
  }

  let itemsHtml = "";
  let totalDets = 0;

  for (const [camName, dets] of Object.entries(detectionsMap)) {
    if (!dets || dets.length === 0) continue;
    for (const d of dets) {
      if (d.category !== activeCategory) continue;
      totalDets++;

      let tags = "";
      if (d.speed_kmh) {
        tags += `<span class="tag speed">${Math.round(d.speed_kmh)} km/h</span>`;
      }
      if (d.plate) {
        tags += `<span class="tag plate">Plate: ${d.plate}</span>`;
      }

      itemsHtml += `
        <div class="detection-item ${d.category}">
          <div class="detection-row-top">
            <span>${camName}</span>
            <span style="color: var(--accent-primary);">${Math.round(d.confidence * 100)}%</span>
          </div>
          <div style="font-size: 0.86rem; font-weight: 500;">
            ${d.label.charAt(0).toUpperCase() + d.label.slice(1)}
          </div>
          ${tags ? `<div class="detection-meta-tags">${tags}</div>` : ""}
        </div>
      `;
    }
  }

  if (totalDets === 0) {
    container.innerHTML = `<div style="color: var(--text-muted); font-size: 0.82rem; text-align: center; padding: 1.5rem 0;">No active ${activeCategory} detections in view.</div>`;
  } else {
    container.innerHTML = itemsHtml;
  }
}
