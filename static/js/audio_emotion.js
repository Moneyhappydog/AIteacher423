/* Audio emotion recording and recognition */

// Fixed smoothing coefficient
const SMOOTH_COEFF = 0.60;

// Smoothed scores (exponential moving average)
let smoothedScores = null;

const EMOTION_COLORS = {
  happy:   '#FFD166',
  sad:     '#4D9DE0',
  angry:   '#FF6B6B',
  neutral: '#A8DADC'
};
const EMOTION_LABELS_CN_MAP = {
  happy: '开心', sad: '难过', angry: '生气', neutral: '平静'
};
// 各情绪置信度展示用：后端返回的英文键 -> 中文标签（与 AUDIO_LABELS 一致）
const EMOTION_EN_TO_CN = {
  anger: '生气', fear: '恐惧', happy: '高兴', neutral: '中性', sad: '难过', surprise: '惊讶'
};

// Per-emotion state: { mediaRecorder, audioBlob, audioUrl, chunks, isRecording, timerInterval }
const state = {
  happy:   { mediaRecorder: null, audioBlob: null, audioUrl: null, chunks: [], isRecording: false, timerInterval: null },
  sad:     { mediaRecorder: null, audioBlob: null, audioUrl: null, chunks: [], isRecording: false, timerInterval: null },
  angry:   { mediaRecorder: null, audioBlob: null, audioUrl: null, chunks: [], isRecording: false, timerInterval: null },
  neutral: { mediaRecorder: null, audioBlob: null, audioUrl: null, chunks: [], isRecording: false, timerInterval: null }
};

const analysisResults = {};

// ── Waveform drawing ──────────────────────────────────────────────────────────
function drawWaveform(canvasId, analyser) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const bufLen = analyser.frequencyBinCount;
  const dataArr = new Uint8Array(bufLen);
  canvas.width  = canvas.offsetWidth  || 300;
  canvas.height = canvas.offsetHeight || 80;

  function draw() {
    if (!analyser) return;
    requestAnimationFrame(draw);
    analyser.getByteTimeDomainData(dataArr);
    ctx.fillStyle = '#1a1a2e';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#7C3AED';
    ctx.beginPath();
    const sliceW = canvas.width / bufLen;
    let x = 0;
    for (let i = 0; i < bufLen; i++) {
      const v = dataArr[i] / 128.0;
      const y = v * (canvas.height / 2);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      x += sliceW;
    }
    ctx.lineTo(canvas.width, canvas.height / 2);
    ctx.stroke();
  }
  draw();
}

function drawFlatWave(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  canvas.width  = canvas.offsetWidth  || 300;
  canvas.height = canvas.offsetHeight || 80;
  ctx.fillStyle = '#1a1a2e';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = '#7C3AED';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(0, canvas.height / 2);
  ctx.lineTo(canvas.width, canvas.height / 2);
  ctx.stroke();
}

// ── Record / Stop ─────────────────────────────────────────────────────────────
async function toggleRecord(key, label, color) {
  const s = state[key];
  if (s.isRecording) {
    stopRecording(key);
  } else {
    await startRecording(key, label, color);
  }
}

async function startRecording(key, label, color) {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const s = state[key];

    // Live waveform via AudioContext
    const audioCtx = new AudioContext();
    const source   = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    s._analyser = analyser;
    s._audioCtx = audioCtx;
    drawWaveform('wave_' + key, analyser);

    s.chunks = [];
    s.mediaRecorder = new MediaRecorder(stream);
    s.mediaRecorder.ondataavailable = e => { if (e.data.size > 0) s.chunks.push(e.data); };
    s.mediaRecorder.onstop = () => onRecordingStop(key, stream, audioCtx);
    s.mediaRecorder.start();
    s.isRecording = true;

    // UI updates
    const btn = document.getElementById('recBtn_' + key);
    btn.textContent = '⏹';
    btn.classList.add('recording-pulse');
    document.getElementById('recStatus_' + key).textContent = '录音中...';
    document.getElementById('playArea_' + key).classList.add('d-none');

    // Timer
    let secs = 0;
    const timerEl = document.getElementById('recTimer_' + key);
    const secSpan = timerEl.querySelector('span');
    timerEl.classList.remove('d-none');
    s.timerInterval = setInterval(() => {
      secs++;
      secSpan.textContent = secs;
      if (secs >= 10) stopRecording(key); // auto-stop at 10s
    }, 1000);

  } catch (err) {
    alert('无法访问麦克风：' + err.message);
  }
}

function stopRecording(key) {
  const s = state[key];
  if (s.mediaRecorder && s.mediaRecorder.state !== 'inactive') {
    s.mediaRecorder.stop();
  }
  s.isRecording = false;
  clearInterval(s.timerInterval);
  document.getElementById('recTimer_' + key).classList.add('d-none');
  const btn = document.getElementById('recBtn_' + key);
  btn.textContent = '🎙️';
  btn.classList.remove('recording-pulse');
  document.getElementById('recStatus_' + key).textContent = '录音完成！';
}

function onRecordingStop(key, stream, audioCtx) {
  const s = state[key];
  stream.getTracks().forEach(t => t.stop());
  audioCtx.close();

  const blob = new Blob(s.chunks, { type: 'audio/webm' });
  s.audioBlob = blob;
  s.audioUrl  = URL.createObjectURL(blob);

  const audioEl = document.getElementById('audio_' + key);
  audioEl.src = s.audioUrl;
  document.getElementById('playArea_' + key).classList.remove('d-none');

  // Draw static waveform after recording
  drawFlatWave('wave_' + key);
  drawAudioWaveform(key, blob);
  updateGallery();
}

// Draw waveform from recorded blob
async function drawAudioWaveform(key, blob) {
  try {
    const arrayBuffer = await blob.arrayBuffer();
    const audioCtx    = new OfflineAudioContext(1, 1, 44100);
    const audioBuf    = await audioCtx.decodeAudioData(arrayBuffer);
    const data        = audioBuf.getChannelData(0);

    const canvas = document.getElementById('wave_' + key);
    const ctx    = canvas.getContext('2d');
    canvas.width  = canvas.offsetWidth  || 300;
    canvas.height = canvas.offsetHeight || 80;
    ctx.fillStyle = '#1a1a2e';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = EMOTION_COLORS[key] || '#7C3AED';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    const step = Math.floor(data.length / canvas.width);
    for (let x = 0; x < canvas.width; x++) {
      const v = data[x * step] || 0;
      const y = ((v + 1) / 2) * canvas.height;
      x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();
  } catch (_) {}
}

// ── Gallery ──────────────────────────────────────────────────────────────────
function updateGallery() {
  const list = document.getElementById('galleryList');
  const hasAny = Object.values(state).some(s => s.audioUrl);
  if (!hasAny) return;

  let html = '';
  const emotionOrder = ['happy', 'sad', 'angry', 'neutral'];
  emotionOrder.forEach(key => {
    const s = state[key];
    if (!s.audioUrl) return;
    const result = analysisResults[key];
    const label  = EMOTION_LABELS_CN_MAP[key];
    const color  = EMOTION_COLORS[key];
    html += `
      <div class="gallery-item">
        <div class="gallery-item-header">
          <span style="font-size:1.3rem">${getEmoji(key)}</span>
          <span style="color:${color}">${label}情绪版</span>
          ${result ? `<span class="ms-auto badge" style="background:${color}20;color:${color}">${result.emotion_cn} ${result.emoji || ''}</span>` : ''}
        </div>
        <audio src="${s.audioUrl}" controls style="width:100%;border-radius:8px;height:36px"></audio>
      </div>`;
  });
  list.innerHTML = html;
}

function getEmoji(key) {
  return { happy:'😊', sad:'😢', angry:'😠', neutral:'😐' }[key] || '🎵';
}

// ── Analysis ──────────────────────────────────────────────────────────────────
async function analyzeRecording(key, label) {
  const s = state[key];
  if (!s.audioBlob) { alert('请先录音！'); return; }

  const resultArea = document.getElementById('resultArea');
  const isFirstCall = !window._audioModelWarmed;
  resultArea.innerHTML = `
    <div class="text-center py-4">
      <div class="spinner-border text-primary"></div>
      <p class="mt-2 fw-bold">AI 正在聆听你的声音...</p>
      ${isFirstCall ? '<p class="text-muted small">首次分析需要加载模型，约需 10~30 秒，请耐心等待 🕐</p>' : ''}
    </div>`;

  try {
    // Convert webm recording to 16kHz mono WAV
    const wavBlob  = await convertToWav(s.audioBlob);
    const formData = new FormData();
    formData.append('audio', wavBlob, 'recording.wav');

    // 添加模型ID
    const modelId = getCurrentModelId ? getCurrentModelId() : null;
    if (modelId) {
      formData.append('model_id', modelId);
    }

    const resp = await fetch('/audio/predict', { method: 'POST', body: formData });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`服务器错误 ${resp.status}: ${text.slice(0, 200)}`);
    }
    const data = await resp.json();

    if (data.error) {
      resultArea.innerHTML = `<div class="alert alert-danger">⚠️ ${data.error}</div>`;
      return;
    }

    window._audioModelWarmed = true;
    analysisResults[key] = data;
    displayResult(data, label);
    updateGallery();
    updateComparisonChart();
  } catch (err) {
    resultArea.innerHTML = `
      <div class="alert alert-danger">
        <strong>请求失败：</strong>${err.message}<br>
        <small class="text-muted">如果是首次识别，请稍等片刻后重试（模型加载中）</small>
      </div>`;
  }
}

function displayResult(data, recordedLabel) {
  const resultArea = document.getElementById('resultArea');
  let scores = data.scores || {};

  // Apply smoothing
  scores = applySmoothing(scores);

  // Find the emotion with highest confidence
  const filteredScores = {};
  let maxKey = null, maxVal = -Infinity;
  for (const [k, v] of Object.entries(scores)) {
    filteredScores[k] = v;
    if (v > maxVal) { maxVal = v; maxKey = k; }
  }

  // 直接使用最高置信度的情绪
  const displayEmotion = data.emotion_cn || '未知';
  const displayEmoji = data.emoji || '🤖';

  // 检查是否匹配录制的情绪标签
  const isCorrect = (data.emotion_cn === recordedLabel) || matchesLabel(data.emotion_cn, recordedLabel);

  const labelFor = (en) => EMOTION_EN_TO_CN[en] || en;
  let scoresHtml = Object.entries(filteredScores).map(([name, score]) => {
    const cn = labelFor(name);
    const barWidth = (score * 100).toFixed(1);
    const isTop = name === maxKey;
    return `
    <div class="mb-1">
      <div class="d-flex justify-content-between small fw-bold">
        <span>${cn}${isTop ? ' ⭐' : ''}</span><span>${(score * 100).toFixed(1)}%</span>
      </div>
      <div class="score-bar-bg">
        <div class="score-bar" style="width:${barWidth}%;background:${getColorForEmotion(cn)}"></div>
      </div>
    </div>`;
  }).join('');

  resultArea.innerHTML = `
    <div class="result-card text-center mb-3">
      <div class="result-emotion-big">${displayEmoji}</div>
      <div class="result-label-big">${displayEmotion}</div>
      <div class="text-muted small">AI 判断你表达的情绪是：<strong>${displayEmotion}</strong></div>
      <div class="mt-2 p-2 rounded" style="background:${isCorrect ? '#ECFDF5' : '#FEF2F2'}">
        ${isCorrect
          ? `✅ <strong>猜对了！</strong>你录的是"${recordedLabel}"，AI 也识别出来了！`
          : `🤔 你录的是"${recordedLabel}"，AI 识别为"${displayEmotion}"，继续练习吧！`
        }
      </div>
    </div>
    <div class="mt-2">
      <div class="fw-bold mb-2 small">各情绪置信度：</div>
      ${scoresHtml}
    </div>`;
}

function matchesLabel(cnResult, cnRecorded) {
  const map = { '愤怒': '生气', '生气': '愤怒', '悲伤': '难过', '高兴': '开心' };
  return map[cnResult] === cnRecorded || map[cnRecorded] === cnResult;
}

function getColorForEmotion(name) {
  const map = {
    '生气': '#FF6B6B', '害怕': '#C77DFF', '恐惧': '#C77DFF',
    '开心': '#FFD166', '高兴': '#FFD166',
    '平静': '#A8DADC', '中性': '#A8DADC',
    '难过': '#4D9DE0', '惊讶': '#3BB273'
  };
  return map[name] || '#7C3AED';
}

// ── Comparison Chart ──────────────────────────────────────────────────────────
function updateComparisonChart() {
  const area = document.getElementById('comparisonArea');
  const chartDiv = document.getElementById('comparisonChart');
  const keys = Object.keys(analysisResults);
  if (keys.length < 2) { area.style.display = 'none'; return; }
  area.style.display = '';

  // Simple bar comparison for each recorded emotion
  let html = '';
  keys.forEach(key => {
    const r = analysisResults[key];
    const recordedLabel = EMOTION_LABELS_CN_MAP[key];
    html += `
      <div class="col-md-6">
        <div style="background:#F9FAFB;border-radius:12px;padding:0.8rem">
          <div class="fw-bold mb-1">${getEmoji(key)} ${recordedLabel}版</div>
          <div class="small text-muted">AI识别: <strong>${r.emotion_cn}</strong> ${r.emoji || ''}</div>
        </div>
      </div>`;
  });
  chartDiv.innerHTML = html;
}

// Fixed confidence threshold
const CONFIDENCE_THRESHOLD = 0.30;

// Apply smoothing (exponential moving average)
function applySmoothing(scores) {
  if (!smoothedScores) {
    smoothedScores = {};
    for (const [k, v] of Object.entries(scores)) smoothedScores[k] = v;
    return smoothedScores;
  }
  for (const [k, v] of Object.entries(scores)) {
    smoothedScores[k] = SMOOTH_COEFF * v + (1 - SMOOTH_COEFF) * (smoothedScores[k] || v);
  }
  return smoothedScores;
}

// ── Show Message ──────────────────────────────────────────────────────────────
function showAudioMsg(msg, type) {
  const el = document.getElementById('audioMsg');
  if (!el) return;
  el.classList.remove('d-none');
  el.textContent = msg;
  const colors = { success: '#ECFDF5', warning: '#FFFBEB', error: '#FEF2F2', info: '#EFF6FF' };
  el.style.background = colors[type] || colors.info;
  setTimeout(() => el.classList.add('d-none'), 3500);
}

// ── Clear Recording ───────────────────────────────────────────────────────────
function clearRecording(key) {
  const s = state[key];
  s.audioBlob = null;
  s.audioUrl  = null;
  s.chunks    = [];
  delete analysisResults[key];
  document.getElementById('playArea_' + key).classList.add('d-none');
  document.getElementById('recStatus_' + key).textContent = '点击录音';
  drawFlatWave('wave_' + key);
  updateGallery();
}

// ── WAV Converter ─────────────────────────────────────────────────────────────
async function convertToWav(blob) {
  const TARGET_SR = 16000;

  // Step 1: decode at the browser's native sample rate (no sampleRate hint —
  //         most browsers ignore it and still use 44100/48000 anyway)
  const arrayBuffer = await blob.arrayBuffer();
  const decodeCtx   = new AudioContext();
  const audioBuf    = await decodeCtx.decodeAudioData(arrayBuffer);
  await decodeCtx.close();

  // Step 2: resample to 16 kHz mono via OfflineAudioContext.
  //   numSamples must be calculated from the *duration*, not audioBuf.length,
  //   so that the OfflineAudioContext has exactly enough frames at TARGET_SR.
  const numSamples = Math.ceil(audioBuf.duration * TARGET_SR);
  const offlineCtx = new OfflineAudioContext(1, numSamples, TARGET_SR);
  const source     = offlineCtx.createBufferSource();
  source.buffer    = audioBuf;
  source.connect(offlineCtx.destination);
  source.start(0);
  const rendered   = await offlineCtx.startRendering();
  const pcmData    = rendered.getChannelData(0);

  return encodeWav(pcmData, TARGET_SR, 1);
}

function encodeWav(samples, sampleRate, numChannels) {
  const bitDepth    = 16;
  const byteRate    = sampleRate * numChannels * bitDepth / 8;
  const blockAlign  = numChannels * bitDepth / 8;
  const dataSize    = samples.length * blockAlign;
  const buffer      = new ArrayBuffer(44 + dataSize);
  const view        = new DataView(buffer);

  function writeStr(o, s) { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); }
  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);         // PCM
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitDepth, true);
  writeStr(36, 'data');
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    offset += 2;
  }
  return new Blob([buffer], { type: 'audio/wav' });
}

// Init waveforms on load
document.addEventListener('DOMContentLoaded', () => {
  ['happy','sad','angry','neutral'].forEach(k => drawFlatWave('wave_' + k));
});
