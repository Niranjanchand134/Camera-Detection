/**
 * Crimson Vision - Records & Reports Controller
 * Instant Auto-filtering for Detections & Table View for Saved Video Recordings
 */

let currentPage = 1;
const perPage = 15;

let debounceTimer = null;
function debounce(fn, delay = 350) {
  return function (...args) {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => fn.apply(this, args), delay);
  };
}

document.addEventListener("DOMContentLoaded", () => {
  loadRecords();
  loadRecordings();
  setupAutoFilters();
});

function setupAutoFilters() {
  // Detection Records Filters
  const camEl = document.getElementById("filter-camera");
  const catEl = document.getElementById("filter-category");
  const plateEl = document.getElementById("filter-plate");
  const speedEl = document.getElementById("filter-speed");
  const startEl = document.getElementById("filter-start-time");
  const endEl = document.getElementById("filter-end-time");

  const triggerSearch = debounce(() => loadRecords(1), 350);

  camEl?.addEventListener("change", () => loadRecords(1));
  catEl?.addEventListener("change", () => loadRecords(1));
  startEl?.addEventListener("change", () => loadRecords(1));
  endEl?.addEventListener("change", () => loadRecords(1));
  plateEl?.addEventListener("input", triggerSearch);
  speedEl?.addEventListener("input", triggerSearch);

  // Video Recordings Manual Typing Search Filter
  const recSearchEl = document.getElementById("rec-filter-search");
  const triggerRecSearch = debounce(() => loadRecordings(), 300);
  recSearchEl?.addEventListener("input", triggerRecSearch);
}

function resetRecSearch() {
  const recSearchEl = document.getElementById("rec-filter-search");
  if (recSearchEl) {
    recSearchEl.value = "";
    loadRecordings();
  }
}

function getFilterParams() {
  const camera = document.getElementById("filter-camera").value;
  const category = document.getElementById("filter-category").value;
  const plate = document.getElementById("filter-plate").value.trim();
  const minSpeed = document.getElementById("filter-speed").value.trim();
  const startTime = document.getElementById("filter-start-time").value;
  const endTime = document.getElementById("filter-end-time").value;

  const params = new URLSearchParams();
  if (camera) params.append("camera", camera);
  if (category && category !== "all") params.append("category", category);
  if (plate) params.append("plate", plate);
  if (minSpeed) params.append("min_speed", minSpeed);
  if (startTime) params.append("start_time", startTime.replace("T", " "));
  if (endTime) params.append("end_time", endTime.replace("T", " "));

  return params;
}

async function loadRecords(page = 1) {
  currentPage = page;
  const params = getFilterParams();
  params.append("page", currentPage);
  params.append("per_page", perPage);

  const tbody = document.getElementById("records-table-body");
  tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 2rem; color: var(--text-muted);">Loading detection records...</td></tr>`;

  try {
    const res = await fetch(`/api/records?${params.toString()}`);
    const result = await res.json();

    if (result.status !== "success") {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 2rem; color: var(--accent-crimson);">Error loading records.</td></tr>`;
      return;
    }

    const { events, total, total_pages } = result.data;
    const stats = result.stats;

    // Update Stats Numbers
    if (stats) {
      document.getElementById("stat-total-events").textContent = stats.total_events || 0;
      document.getElementById("stat-vehicles").textContent = stats.vehicle_count || 0;
      document.getElementById("stat-persons").textContent = stats.person_count || 0;
      document.getElementById("stat-plates").textContent = stats.plate_count || 0;
    }

    document.getElementById("table-total-badge").textContent = `${total} Total Matches`;

    if (events.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">No records found matching current criteria.</td></tr>`;
    } else {
      let rowsHtml = "";
      events.forEach((ev) => {
        const snapHtml = ev.snapshot_filename
          ? `<img src="/snapshots/${ev.snapshot_filename}" alt="Snap" class="snapshot-thumb" title="Click to enlarge" onclick="openSnapshotModal('/snapshots/${ev.snapshot_filename}', '${ev.camera_name} - ${ev.label}')">`
          : `<span style="color: var(--text-muted); font-size: 0.75rem;">No Image</span>`;

        const speedHtml = (ev.speed_kmh !== null && ev.speed_kmh !== undefined)
          ? `<span class="tag speed">${ev.speed_kmh} km/h</span>`
          : `<span style="color: var(--text-muted);">--</span>`;

        const plateHtml = ev.plate_text
          ? `<span class="tag plate">${ev.plate_text}</span>`
          : `<span style="color: var(--text-muted);">--</span>`;

        rowsHtml += `
          <tr id="row-event-${ev.id}">
            <td>${snapHtml}</td>
            <td style="font-family: monospace; font-size: 0.8rem; color: #cbd5e1;">${ev.timestamp}</td>
            <td><strong>${ev.camera_name}</strong></td>
            <td>
              <span class="category-badge ${ev.category}">
                ${ev.label ? ev.label.toUpperCase() : ev.category.toUpperCase()}
              </span>
            </td>
            <td>${Math.round(ev.confidence * 100)}%</td>
            <td>${speedHtml}</td>
            <td>${plateHtml}</td>
            <td style="text-align: right;">
              <div class="row-actions">
                ${ev.snapshot_filename ? `
                  <button type="button" class="action-btn" style="padding: 0.22rem 0.55rem; font-size: 0.74rem;" onclick="openSnapshotModal('/snapshots/${ev.snapshot_filename}', '${ev.camera_name} - ${ev.label}')">
                    View
                  </button>
                ` : ""}
                <button type="button" class="action-btn danger" style="padding: 0.22rem 0.55rem; font-size: 0.74rem;" title="Delete Record" onclick="deleteRecord(${ev.id})">
                  Delete
                </button>
              </div>
            </td>
          </tr>
        `;
      });
      tbody.innerHTML = rowsHtml;
    }

    // Update Pagination Bar
    document.getElementById("pagination-info").textContent = `Page ${currentPage} of ${total_pages} (${total} items)`;
    document.getElementById("btn-prev-page").disabled = currentPage <= 1;
    document.getElementById("btn-next-page").disabled = currentPage >= total_pages;

  } catch (err) {
    console.error("Failed to fetch records:", err);
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 2rem; color: var(--accent-crimson);">Failed to load records. Check network.</td></tr>`;
  }
}

function applyFilter() {
  loadRecords(1);
}

function resetFilters() {
  document.getElementById("filter-form").reset();
  loadRecords(1);
}

function changePage(delta) {
  loadRecords(currentPage + delta);
}

function exportCSV() {
  const params = getFilterParams();
  window.location.href = `/api/records/export?${params.toString()}`;
}

// ---------------- DELETION HANDLERS ----------------
async function deleteRecord(eventId) {
  if (!confirm(`Are you sure you want to delete detection record #${eventId}?`)) {
    return;
  }

  try {
    const res = await fetch(`/api/records/${eventId}`, {
      method: "DELETE"
    });
    const data = await res.json();
    if (data.status === "success") {
      loadRecords(currentPage);
    } else {
      alert("Could not delete record: " + (data.message || "Unknown error"));
    }
  } catch (err) {
    console.error("Delete record error:", err);
    alert("Network error while deleting record.");
  }
}

async function deleteAllRecords() {
  const answer = confirm("WARNING: This will permanently delete ALL detection events and snapshot images.\n\nDo you want to proceed?");
  if (!answer) return;

  try {
    const res = await fetch("/api/records/all", {
      method: "DELETE"
    });
    const data = await res.json();
    if (data.status === "success") {
      loadRecords(1);
    } else {
      alert("Error deleting all records.");
    }
  } catch (err) {
    console.error("Delete all records error:", err);
    alert("Network error while deleting all records.");
  }
}

async function deleteRecording(relPath) {
  if (!confirm(`Are you sure you want to delete video recording "${relPath}"?`)) {
    return;
  }

  try {
    const res = await fetch(`/api/recordings/${encodeURIComponent(relPath)}`, {
      method: "DELETE"
    });
    const data = await res.json();
    if (data.status === "success") {
      loadRecordings();
    } else {
      alert("Could not delete video file.");
    }
  } catch (err) {
    console.error("Delete video error:", err);
    alert("Network error while deleting video.");
  }
}

async function deleteAllRecordings() {
  const searchInput = document.getElementById("rec-filter-search");
  const query = searchInput ? searchInput.value.trim() : "";

  let msg = "WARNING: This will delete video recordings matching current search filter.";
  if (query) {
    msg += `\n- Search filter: "${query}"`;
  } else {
    msg = "WARNING: This will permanently delete ALL saved video recordings across all cameras!";
  }
  msg += "\n\nDo you want to proceed?";

  if (!confirm(msg)) return;

  try {
    const params = new URLSearchParams();
    if (query) params.append("q", query);

    const res = await fetch(`/api/recordings/all?${params.toString()}`, {
      method: "DELETE"
    });
    const data = await res.json();
    if (data.status === "success") {
      loadRecordings();
    } else {
      alert("Error deleting recordings.");
    }
  } catch (err) {
    console.error("Delete all recordings error:", err);
    alert("Network error while deleting all recordings.");
  }
}

// ---------------- RECORDINGS ARCHIVE (TABLE VIEW & TYPING SEARCH) ----------------
async function loadRecordings() {
  const tbody = document.getElementById("recordings-table-body");
  const countBadge = document.getElementById("recordings-count-badge");
  const searchInput = document.getElementById("rec-filter-search");
  const query = searchInput ? searchInput.value.trim() : "";

  tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 2rem; color: var(--text-muted);">Loading video recordings...</td></tr>`;

  try {
    const params = new URLSearchParams();
    if (query) params.append("q", query);

    const res = await fetch(`/api/recordings?${params.toString()}`);
    const data = await res.json();
    const files = data.recordings || [];

    if (countBadge) {
      countBadge.textContent = `${files.length} Clips Found`;
    }

    if (files.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">No video recordings found matching "${query || 'all'}".</td></tr>`;
      return;
    }

    let rowsHtml = "";
    files.forEach((rec) => {
      rowsHtml += `
        <tr>
          <td style="font-family: monospace; font-size: 0.8rem; color: #cbd5e1;">${rec.created_at}</td>
          <td>
            <span class="category-badge vehicle" style="font-size: 0.72rem;">${rec.camera}</span>
          </td>
          <td style="font-family: monospace; font-size: 0.78rem; color: var(--text-primary);" title="${rec.filename}">
            ${rec.filename}
          </td>
          <td><strong>${rec.size_mb} MB</strong></td>
          <td>
            <span class="tag" style="background: rgba(16, 185, 129, 0.15); color: #34d399; font-size: 0.72rem;">Synced AAC</span>
          </td>
          <td style="text-align: right;">
            <div class="row-actions">
              <button type="button" class="action-btn primary" style="padding: 0.22rem 0.6rem; font-size: 0.74rem;" onclick="playVideoModal('${rec.url}', '${rec.camera} - ${rec.created_at}')">
                Play
              </button>
              <a href="${rec.url}" download="${rec.filename}" class="action-btn" style="padding: 0.22rem 0.6rem; font-size: 0.74rem; text-decoration: none;">
                Download
              </a>
              <button type="button" class="action-btn danger" style="padding: 0.22rem 0.6rem; font-size: 0.74rem;" title="Delete video" onclick="deleteRecording('${rec.rel_path}')">
                Delete
              </button>
            </div>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = rowsHtml;
  } catch (err) {
    console.error("Error loading recordings:", err);
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 2rem; color: var(--accent-crimson);">Failed to load recordings list. Check network.</td></tr>`;
  }
}

// ---------------- MEDIA MODAL HANDLERS ----------------
function openSnapshotModal(imgSrc, title) {
  const modal = document.getElementById("media-modal");
  const modalTitle = document.getElementById("modal-title");
  const wrapper = document.getElementById("modal-content-wrapper");

  modalTitle.textContent = `Event Snapshot: ${title}`;
  wrapper.innerHTML = `<img src="${imgSrc}" alt="Snapshot" class="modal-media">`;
  modal.classList.add("open");
}

function playVideoModal(videoSrc, title) {
  const modal = document.getElementById("media-modal");
  const modalTitle = document.getElementById("modal-title");
  const wrapper = document.getElementById("modal-content-wrapper");

  modalTitle.textContent = `Video Player: ${title}`;
  wrapper.innerHTML = `
    <div style="position: relative;">
      <video controls autoplay playsinline preload="auto" class="modal-media" id="modal-video-player">
        <source src="${videoSrc}" type="video/mp4">
        Your browser does not support HTML5 video playback.
      </video>
      <div id="video-load-overlay" style="position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.6); border-radius: var(--radius-md); margin-top: 1rem; pointer-events: none;">
        <span style="color: var(--text-secondary); font-size: 0.9rem;">Loading video...</span>
      </div>
    </div>
  `;
  modal.classList.add("open");

  const videoEl = document.getElementById("modal-video-player");
  const loadOverlay = document.getElementById("video-load-overlay");

  if (videoEl) {
    videoEl.addEventListener("canplay", () => {
      if (loadOverlay) loadOverlay.style.display = "none";
    });
    videoEl.addEventListener("error", () => {
      if (loadOverlay) {
        loadOverlay.innerHTML = `<span style="color: var(--accent-crimson); font-size: 0.9rem;">⚠ Playback error. <a href="${videoSrc}" download style="color: var(--accent-primary); text-decoration: underline;">Download file</a> to view locally.</span>`;
        loadOverlay.style.pointerEvents = "auto";
      }
    });
  }
}

function closeModal(event) {
  if (event.target.id === "media-modal") {
    closeModalDirect();
  }
}

function closeModalDirect() {
  const modal = document.getElementById("media-modal");
  const wrapper = document.getElementById("modal-content-wrapper");
  const video = wrapper.querySelector("video");
  if (video) {
    video.pause();
    video.removeAttribute("src");
    video.load();
  }
  wrapper.innerHTML = "";
  modal.classList.remove("open");
}
