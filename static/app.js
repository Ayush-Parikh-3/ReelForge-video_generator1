// State Management
let currentJobId = null;
let pollInterval = null;
let currentAspectRatio = "16:9";
let currentStoryboard = null;

// DOM Elements
const promptInput = document.getElementById("promptInput");
const styleSelect = document.getElementById("styleSelect");
const voiceSelect = document.getElementById("voiceSelect");
const sceneCountSlider = document.getElementById("sceneCountSlider");
const sceneCountVal = document.getElementById("sceneCountVal");
const subtitleColor = document.getElementById("subtitleColor");
const musicToggle = document.getElementById("musicToggle");
const aspectRatioGroup = document.getElementById("aspectRatioGroup");

const generateVideoBtn = document.getElementById("generateVideoBtn");
const generateScriptBtn = document.getElementById("generateScriptBtn");
const previewVoiceBtn = document.getElementById("previewVoiceBtn");

const progressSection = document.getElementById("progressSection");
const progressTitle = document.getElementById("progressTitle");
const progressMessage = document.getElementById("progressMessage");
const progressPercent = document.getElementById("progressPercent");
const progressFill = document.getElementById("progressFill");
const terminalLogs = document.getElementById("terminalLogs");

const stepScript = document.getElementById("stepScript");
const stepVoice = document.getElementById("stepVoice");
const stepVisuals = document.getElementById("stepVisuals");
const stepRender = document.getElementById("stepRender");

const storyboardSection = document.getElementById("storyboardSection");
const scenesContainer = document.getElementById("scenesContainer");
const renderStoryboardBtn = document.getElementById("renderStoryboardBtn");
const sbTitle = document.getElementById("sbTitle");

const resultSection = document.getElementById("resultSection");
const resultTitle = document.getElementById("resultTitle");
const finalVideoPlayer = document.getElementById("finalVideoPlayer");
const downloadVideoBtn = document.getElementById("downloadVideoBtn");
const sceneCardsScroll = document.getElementById("sceneCardsScroll");
const newVideoBtn = document.getElementById("newVideoBtn");
const videoContainer = document.getElementById("videoContainer");

const settingsModal = document.getElementById("settingsModal");
const settingsBtn = document.getElementById("settingsBtn");
const closeSettingsBtn = document.getElementById("closeSettingsBtn");
const saveSettingsBtn = document.getElementById("saveSettingsBtn");
const geminiApiKey = document.getElementById("geminiApiKey");

const historyModal = document.getElementById("historyModal");
const historyBtn = document.getElementById("historyBtn");
const closeHistoryBtn = document.getElementById("closeHistoryBtn");
const historyList = document.getElementById("historyList");

const statusText = document.getElementById("statusText");
const ffmpegStatus = document.getElementById("ffmpegStatus");
const previewAudio = document.getElementById("previewAudio");

// Initialize Application
document.addEventListener("DOMContentLoaded", async () => {
  loadStoredSettings();
  setupEventListeners();
  await checkSystemStatus();
  const savedJob = localStorage.getItem("active_job_id");
  if (savedJob) {
    checkActiveJob(savedJob);
  }
});

function loadStoredSettings() {
  const savedKey = localStorage.getItem("gemini_api_key");
  if (savedKey) {
    geminiApiKey.value = savedKey;
  }
  const savedImgKey = localStorage.getItem("image_api_key");
  const imgInput = document.getElementById("imageApiKey");
  if (savedImgKey && imgInput) {
    imgInput.value = savedImgKey;
  }
}

async function checkSystemStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    
    if (data.ffmpeg && data.ffmpeg.ready) {
      statusText.textContent = "FFmpeg Engine Ready";
    } else {
      statusText.textContent = "FFmpeg Bundled";
    }

    // Populate Voices
    if (data.voices) {
      voiceSelect.innerHTML = data.voices.map(v => 
        `<option value="${v.id}">${v.name}</option>`
      ).join("");
    }
  } catch (err) {
    console.warn("Status check warning:", err);
    statusText.textContent = "Offline / Local Mode";
  }
}

function setupEventListeners() {
  // Aspect Ratio Toggles
  aspectRatioGroup.querySelectorAll(".toggle-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      aspectRatioGroup.querySelectorAll(".toggle-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentAspectRatio = btn.dataset.val;
    });
  });

  // Scene Count Slider
  sceneCountSlider.addEventListener("input", (e) => {
    const val = e.target.value;
    const estSec = val * 6;
    sceneCountVal.textContent = `${val} scenes (~${estSec}s)`;
  });

  // Inspiration Chips
  document.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      promptInput.value = chip.dataset.prompt;
      promptInput.focus();
    });
  });

  // Voice Preview
  previewVoiceBtn.addEventListener("click", async () => {
    const voiceId = voiceSelect.value;
    previewVoiceBtn.classList.add("loading");
    try {
      const res = await fetch("/api/preview-voice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice_id: voiceId })
      });
      const data = await res.json();
      if (data.audio_url) {
        previewAudio.src = data.audio_url;
        previewAudio.play();
      }
    } catch (e) {
      alert("Error playing voice preview");
    } finally {
      previewVoiceBtn.classList.remove("loading");
    }
  });

  // Generate Full Video
  generateVideoBtn.addEventListener("click", startFullVideoGeneration);

  // Generate Script First
  generateScriptBtn.addEventListener("click", startScriptGeneration);

  // Render from Storyboard
  renderStoryboardBtn.addEventListener("click", renderFromStoryboard);

  // New Video
  newVideoBtn.addEventListener("click", () => {
    resultSection.classList.add("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  // Settings
  settingsBtn.addEventListener("click", () => settingsModal.classList.remove("hidden"));
  closeSettingsBtn.addEventListener("click", () => settingsModal.classList.add("hidden"));
  saveSettingsBtn.addEventListener("click", () => {
    localStorage.setItem("gemini_api_key", geminiApiKey.value.trim());
    const imgVal = document.getElementById("imageApiKey") ? document.getElementById("imageApiKey").value.trim() : "";
    localStorage.setItem("image_api_key", imgVal);
    settingsModal.classList.add("hidden");
  });

  // History
  historyBtn.addEventListener("click", openHistoryModal);
  closeHistoryBtn.addEventListener("click", () => historyModal.classList.add("hidden"));
}

// Full Video Generation Workflow
async function startFullVideoGeneration() {
  const prompt = promptInput.value.trim();
  if (!prompt) {
    alert("Please enter a video prompt or click an inspiration idea!");
    promptInput.focus();
    return;
  }

  const payload = {
    prompt: prompt,
    scene_count: parseInt(sceneCountSlider.value),
    aspect_ratio: currentAspectRatio,
    style: styleSelect.value,
    voice_id: voiceSelect.value,
    add_music: musicToggle.checked,
    subtitle_color: subtitleColor.value,
    api_key: localStorage.getItem("gemini_api_key") || null,
    image_api_key: localStorage.getItem("image_api_key") || null
  };

  showProgressView();

  try {
    const res = await fetch("/api/generate-full-video", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    currentJobId = data.job_id;
    localStorage.setItem("active_job_id", currentJobId);
    startPolling(currentJobId);
  } catch (err) {
    alert("Failed to start video generation: " + err.message);
    hideProgressView();
  }
}

// Script-Only Workflow
async function startScriptGeneration() {
  const prompt = promptInput.value.trim();
  if (!prompt) {
    alert("Please enter a prompt first!");
    return;
  }

  generateScriptBtn.disabled = true;
  generateScriptBtn.textContent = "Writing Script...";

  try {
    const res = await fetch("/api/generate-script-only", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: prompt,
        scene_count: parseInt(sceneCountSlider.value),
        style: styleSelect.value,
        api_key: localStorage.getItem("gemini_api_key") || null
      })
    });
    const data = await res.json();
    currentStoryboard = data;
    renderStoryboardCards(data);
    storyboardSection.classList.remove("hidden");
    storyboardSection.scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    alert("Error generating script: " + err.message);
  } finally {
    generateScriptBtn.disabled = false;
    generateScriptBtn.innerHTML = '<span class="btn-icon">📝</span><span>Generate & Edit Script First</span>';
  }
}

function renderStoryboardCards(data) {
  sbTitle.textContent = `Script: ${data.title || "Custom Video"}`;
  scenesContainer.innerHTML = "";

  data.scenes.forEach((scene, i) => {
    const card = document.createElement("div");
    card.className = "scene-card-edit";
    card.innerHTML = `
      <div class="scene-badge-col">
        <span class="scene-pill">Scene ${scene.scene_id || (i+1)}</span>
      </div>
      <div class="scene-field-col">
        <label>Spoken Narration (Voiceover & Subtitles)</label>
        <textarea class="sb-narration" rows="3">${scene.narration}</textarea>
      </div>
      <div class="scene-field-col">
        <label>Visual Prompt (Image Generation)</label>
        <textarea class="sb-prompt" rows="3">${scene.visual_prompt}</textarea>
      </div>
    `;
    scenesContainer.appendChild(card);
  });
}

// Render from Storyboard Editor
async function renderFromStoryboard() {
  if (!currentStoryboard) return;

  const cards = scenesContainer.querySelectorAll(".scene-card-edit");
  const scenes = [];
  cards.forEach((card, i) => {
    scenes.push({
      scene_id: i + 1,
      narration: card.querySelector(".sb-narration").value.trim(),
      visual_prompt: card.querySelector(".sb-prompt").value.trim(),
      subtitle_text: card.querySelector(".sb-narration").value.trim()
    });
  });

  const payload = {
    title: currentStoryboard.title || promptInput.value.trim(),
    scenes: scenes,
    aspect_ratio: currentAspectRatio,
    style: styleSelect.value,
    voice_id: voiceSelect.value,
    add_music: musicToggle.checked,
    subtitle_color: subtitleColor.value
  };

  storyboardSection.classList.add("hidden");
  showProgressView();

  try {
    const res = await fetch("/api/render-custom-scenes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    currentJobId = data.job_id;
    localStorage.setItem("active_job_id", currentJobId);
    startPolling(currentJobId);
  } catch (err) {
    alert("Error rendering custom scenes: " + err.message);
    hideProgressView();
  }
}

// Check and restore active job if page was refreshed on mobile
async function checkActiveJob(jobId) {
  try {
    const res = await fetch(`/api/job/${jobId}`);
    if (!res.ok) {
      localStorage.removeItem("active_job_id");
      return;
    }
    const job = await res.json();
    if (!job.completed) {
      currentJobId = jobId;
      showProgressView();
      updateProgressUI(job);
      startPolling(jobId);
    } else if (!job.error) {
      showResultView(job);
      localStorage.removeItem("active_job_id");
    } else {
      localStorage.removeItem("active_job_id");
    }
  } catch (e) {
    localStorage.removeItem("active_job_id");
  }
}

// Polling Job Status
function startPolling(jobId) {
  if (pollInterval) clearInterval(pollInterval);

  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/job/${jobId}`);
      if (!res.ok) return;
      const job = await res.json();

      updateProgressUI(job);

      if (job.completed) {
        clearInterval(pollInterval);
        localStorage.removeItem("active_job_id");
        if (job.error) {
          alert("Rendering failed: " + job.error);
          hideProgressView();
        } else {
          setTimeout(() => showResultView(job), 800);
        }
      }
    } catch (err) {
      console.warn("Polling error:", err);
    }
  }, 1200);
}

function updateProgressUI(job) {
  progressTitle.textContent = getStageTitle(job.stage);
  progressMessage.textContent = job.message;
  progressPercent.textContent = `${job.progress}%`;
  progressFill.style.width = `${job.progress}%`;

  // Stepper Nodes
  stepScript.className = "step-node" + (job.progress >= 10 ? " active" : "") + (job.progress > 25 ? " done" : "");
  stepVoice.className = "step-node" + (job.progress >= 25 ? " active" : "") + (job.progress > 50 ? " done" : "");
  stepVisuals.className = "step-node" + (job.progress >= 50 ? " active" : "") + (job.progress > 75 ? " done" : "");
  stepRender.className = "step-node" + (job.progress >= 75 ? " active" : "") + (job.progress >= 100 ? " done" : "");

  // Update Terminal Logs
  if (job.logs && job.logs.length > 0) {
    terminalLogs.innerHTML = job.logs.map(log => `<div>${escapeHtml(log)}</div>`).join("");
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
  }
}

function getStageTitle(stage) {
  switch (stage) {
    case "scripting": return "Writing Script & Storyboard...";
    case "voiceover": return "Generating Voiceover Narration...";
    case "visuals": return "Synthesizing AI Artwork...";
    case "rendering": return "FFmpeg Motion & Subtitle Rendering...";
    case "assembly": return "Assembling Final Video & Audio Mixing...";
    case "done": return "Video Production Complete!";
    default: return "Processing Video...";
  }
}

function showProgressView() {
  progressSection.classList.remove("hidden");
  resultSection.classList.add("hidden");
  progressFill.style.width = "5%";
  progressPercent.textContent = "5%";
  terminalLogs.innerHTML = "<div>[00:00:00] Initializing video pipeline...</div>";
  progressSection.scrollIntoView({ behavior: "smooth" });
}

function hideProgressView() {
  progressSection.classList.add("hidden");
}

function showResultView(job) {
  progressSection.classList.add("hidden");
  resultSection.classList.remove("hidden");

  const meta = job.metadata || {};
  resultTitle.textContent = meta.title || "Your AI Video";
  resultMeta.textContent = `${meta.duration || 0}s • ${meta.aspect_ratio || "16:9"} • ${meta.style || "Cinematic"} style`;

  finalVideoPlayer.src = job.video_url;
  downloadVideoBtn.href = job.video_url;

  // Aspect ratio adjustment for container
  if (meta.aspect_ratio === "9:16") {
    videoContainer.style.maxWidth = "340px";
    videoContainer.style.margin = "0 auto";
  } else {
    videoContainer.style.maxWidth = "100%";
  }

  // Populate scene cards
  sceneCardsScroll.innerHTML = "";
  if (meta.scenes) {
    meta.scenes.forEach(s => {
      const card = document.createElement("div");
      card.className = "breakdown-card";
      card.innerHTML = `
        <img class="breakdown-img" src="${s.image_file}" alt="Scene ${s.scene_id}" onerror="this.src='/static/placeholder.jpg'">
        <div class="breakdown-info">
          <h5>Scene ${s.scene_id} (${s.duration}s)</h5>
          <p>${escapeHtml(s.narration)}</p>
        </div>
      `;
      sceneCardsScroll.appendChild(card);
    });
  }

  resultSection.scrollIntoView({ behavior: "smooth" });
}

async function openHistoryModal() {
  historyModal.classList.remove("hidden");
  historyList.innerHTML = "<p>Loading past videos...</p>";

  try {
    const res = await fetch("/api/history");
    const data = await res.json();
    if (!data.history || data.history.length === 0) {
      historyList.innerHTML = "<p style='color:var(--text-dim)'>No previous videos found. Generate your first one!</p>";
      return;
    }

    historyList.innerHTML = data.history.map(item => `
      <div class="history-card" onclick="playHistoryVideo('${item.video_url}', '${escapeHtml(item.title)}')">
        <h4 style="font-size:0.9rem; margin-bottom:0.3rem">${escapeHtml(item.title)}</h4>
        <span style="font-size:0.75rem; color:var(--text-muted)">${item.duration}s • ${item.aspect_ratio}</span>
      </div>
    `).join("");
  } catch (e) {
    historyList.innerHTML = "<p>Error loading history</p>";
  }
}

window.playHistoryVideo = function(videoUrl, title) {
  historyModal.classList.add("hidden");
  resultSection.classList.remove("hidden");
  resultTitle.textContent = title;
  finalVideoPlayer.src = videoUrl;
  finalVideoPlayer.play();
  resultSection.scrollIntoView({ behavior: "smooth" });
};

function escapeHtml(text) {
  if (!text) return "";
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return text.replace(/[&<>"']/g, m => map[m]);
}
