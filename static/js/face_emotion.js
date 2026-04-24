/* Face emotion recognition - webcam as live base layer, annotated overlay on top */

const EMOJIS = ['😠','🤢','😨','😊','😢','😮','😐'];

// ── Performance tuning（2026.04.17 12:11备份）────────────────────────────────────────────────────────
// const DETECT_INTERVAL_MS  = 80;   // 检测间隔: 80ms (~12.5 FPS)，兼顾流畅与性能
// const JPEG_QUALITY        = 0.75; // JPEG压缩质量: 0.75，清晰度与传输效率平衡
// const VIDEO_WIDTH         = 640;  // 视频宽度: 640px（原320），提升显示清晰度
// const VIDEO_HEIGHT        = 480;  // 视频高度: 480px（原240），提升显示清晰度
// const MAX_CONCURRENT_REQS = 2;    // 允许最多2个并发请求，避免堆积

// 降低频率，减少请求数
const DETECT_INTERVAL_MS  = 150;   // 改为 150ms (6.7 FPS) - 更流畅
const JPEG_QUALITY        = 0.6;   // 降低到 0.6，减小传输量
const VIDEO_WIDTH         = 480;   // 降低分辨率（从 640→480）
const VIDEO_HEIGHT        = 360;   // 保持 4:3
const MAX_CONCURRENT_REQS = 1;     // 改为 1，避免堆积

let intervalId       = null;
let videoEl, videoCanvas, outputImg;
let isRunning        = false;
let firstFrame       = true;
let inflightCount    = 0;          // 当前有多少个请求在飞行中
let latestReqId      = 0;          // 最新请求ID，用于取消旧请求
let lastFaceResult   = null;
let lastFaceCount    = 0;
let consecutiveNoFaceCount = 0;
let lastFaceEventKeys = {};
let lastFaceEventTimes = {};

// ── Camera ──────────────────────────────────────────────────────────────────
function getSelectedFaceModelId() {
  return typeof getCurrentModelId === 'function' ? getCurrentModelId() : null;
}

function getFaceConfidence(face) {
  if (!face || !Array.isArray(face.scores) || face.scores.length === 0) return null;
  return Math.max(...face.scores);
}

function summarizeFaceResult(face) {
  if (!face) return null;
  return {
    emotion_idx: face.emotion_idx,
    emotion: face.emotion_en || null,
    emotion_cn: face.emotion_cn || null,
    confidence: getFaceConfidence(face)
  };
}

function getFaceEmotionSnapshot() {
  const modelId = getSelectedFaceModelId();
  return {
    current_model: modelId || 'system_default',
    model_id: modelId,
    camera_status: isRunning ? 'running' : 'stopped',
    camera_started: !!isRunning,
    last_result: summarizeFaceResult(lastFaceResult),
    last_face_count: lastFaceCount,
    consecutive_no_face_count: consecutiveNoFaceCount
  };
}

function reportFaceEmotionEvent(eventName, eventType, stepCode, payload) {
  const data = payload || {};
  const throttleMs = eventName === 'face_result_updated' || eventName === 'no_face_detected' ? 1500 : 0;
  const eventKey = `${eventName}:${data.emotion || data.face_count || ''}`;
  const lastKey = lastFaceEventKeys[eventName];
  const lastTime = lastFaceEventTimes[eventName] || 0;
  const now = Date.now();
  if (throttleMs && lastKey === eventKey && now - lastTime < throttleMs) {
    return Promise.resolve({ skipped: true, reason: 'throttled' });
  }
  lastFaceEventKeys[eventName] = eventKey;
  lastFaceEventTimes[eventName] = now;

  if (window.AiContextTracker && stepCode) {
    window.AiContextTracker.setStep(stepCode);
  }
  if (!window.AiCourseBridge) return Promise.resolve({ skipped: true });
  return window.AiCourseBridge.track(eventName, {
    eventType: eventType,
    stepCode: stepCode,
    payload: Object.assign({}, data, {
      snapshot: getFaceEmotionSnapshot()
    })
  });
}

function scheduleFaceEmotionSnapshot(stepCode, delayMs) {
  if (window.AiContextTracker && stepCode) {
    window.AiContextTracker.setStep(stepCode);
  }
  if (window.AiContextTracker && typeof window.AiContextTracker.scheduleSnapshot === 'function') {
    window.AiContextTracker.scheduleSnapshot(delayMs || 500, { stepCode: stepCode });
  } else if (window.AiCourseBridge) {
    window.AiCourseBridge.snapshot({ stepCode: stepCode });
  }
}

window.getFaceEmotionSnapshot = getFaceEmotionSnapshot;
window.reportFaceEmotionEvent = reportFaceEmotionEvent;
window.scheduleFaceEmotionSnapshot = scheduleFaceEmotionSnapshot;

function startCamera() {
  videoEl     = document.getElementById('videoEl');
  videoCanvas = document.getElementById('videoCanvas');
  outputImg   = document.getElementById('outputImg');

  const placeholder = document.getElementById('cameraPlaceholder');
  const startBtn   = document.getElementById('startBtn');
  const stopBtn    = document.getElementById('stopBtn');

  // 使用较低分辨率以提升性能
  navigator.mediaDevices.getUserMedia({
    video: {
      width:  { ideal: VIDEO_WIDTH },
      height: { ideal: VIDEO_HEIGHT },
      frameRate: { ideal: 30 }
    },
    audio: false
  })
    .then(stream => {
      videoEl.srcObject = stream;

      videoEl.onloadedmetadata = () => {
        videoCanvas.width  = VIDEO_WIDTH;
        videoCanvas.height = VIDEO_HEIGHT;

        placeholder.style.display = 'none';
        videoEl.style.display = 'block';

        startBtn.classList.add('d-none');
        stopBtn.classList.remove('d-none');

        isRunning  = true;
        firstFrame = true;
        inflightCount = 0;
        latestReqId = 0;
        setStatus('📡 正在识别中...', '#7C3AED');
        startCaptureLoop();
        reportFaceEmotionEvent('camera_started', 'camera', 'start_camera', {
          interval_ms: DETECT_INTERVAL_MS,
          model_id: getSelectedFaceModelId()
        });
        scheduleFaceEmotionSnapshot('start_camera');
      };
    })
    .catch(err => {
      reportFaceEmotionEvent('camera_error', 'camera', 'start_camera', {
        error: err.message
      });
      setStatus('❌ 无法访问摄像头：' + err.message, '#EF4444');
    });
}

function stopCamera() {
  isRunning = false;
  clearInterval(intervalId);
  intervalId = null;
  firstFrame = true;
  inflightCount = 0;
  latestReqId = 0;

  const startBtn = document.getElementById('startBtn');
  const stopBtn  = document.getElementById('stopBtn');
  startBtn.classList.remove('d-none');
  stopBtn.classList.add('d-none');

  if (videoEl && videoEl.srcObject) {
    videoEl.srcObject.getTracks().forEach(t => t.stop());
    videoEl.srcObject = null;
  }

  videoEl.style.display  = 'none';
  outputImg.style.display = 'none';
  outputImg.classList.remove('visible');
  outputImg.src = '';
  reportFaceEmotionEvent('camera_stopped', 'camera', 'start_camera');
  scheduleFaceEmotionSnapshot('start_camera');

  document.getElementById('cameraPlaceholder').style.display = 'flex';
  document.getElementById('faceCountBadge').textContent = '未检测到人脸';
  setStatus('⏹ 已停止识别', '#6B7280');
}

// ── Capture & Predict ────────────────────────────────────────────────────────
function captureAndPredict() {
  if (!isRunning || !videoEl || videoEl.readyState < 2) return;

  // 限制并发请求数，避免请求堆积导致延迟
  if (inflightCount >= MAX_CONCURRENT_REQS) return;

  // Draw current video frame onto the hidden canvas (quick, no resize needed - already at target res)
  const ctx = videoCanvas.getContext('2d');
  ctx.save();
  ctx.translate(videoCanvas.width, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(videoEl, 0, 0, videoCanvas.width, videoCanvas.height);
  ctx.restore();

  // 使用较低质量JPEG减少传输时间
  const imageB64 = videoCanvas.toDataURL('image/jpeg', JPEG_QUALITY);
  const requestData = { image: imageB64 };
  const modelId = getCurrentModelId();
  if (modelId) {
    requestData.model_id = modelId;
  }

  // 生成唯一请求ID，用于取消旧请求
  const reqId = ++latestReqId;
  inflightCount++;

  fetch('/face/predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestData)
  })
  .then(r => r.json())
  .then(data => {
    inflightCount--;
    if (data.error) return;

    // 只处理最新请求的结果，忽略过期响应
    if (reqId === latestReqId) {
      renderFaceResult(data);
    }
  })
  .catch(() => {
    inflightCount--;
  });
}

function renderFaceResult(data) {
  lastFaceCount = data.face_count || 0;
  // 显示标注图
  if (data.image) {
    outputImg.src = data.image;
    if (firstFrame) {
      outputImg.style.display = 'block';
      requestAnimationFrame(() => {
        requestAnimationFrame(() => outputImg.classList.add('visible'));
      });
      firstFrame = false;
    }
  }

  // 更新人脸计数
  const badge = document.getElementById('faceCountBadge');
  badge.textContent = data.face_count > 0
    ? `检测到 ${data.face_count} 张脸`
    : '未检测到人脸';

  if (data.faces && data.faces.length > 0) {
    const face = data.faces[0];
    lastFaceResult = face;
    consecutiveNoFaceCount = 0;
    updateEmotionUI(face);
    reportFaceEmotionEvent('face_result_updated', 'result', 'view_result', {
      face_count: lastFaceCount,
      emotion: face.emotion_en || null,
      emotion_cn: face.emotion_cn || null,
      confidence: getFaceConfidence(face),
      model_id: getSelectedFaceModelId(),
      model_source: data.model_source || null,
      model_name: data.model_name || null
    });
    scheduleFaceEmotionSnapshot('view_result', 350);
    setStatus('✅ 检测成功！', '#10B981');
  } else {
    lastFaceResult = null;
    consecutiveNoFaceCount += 1;
    reportFaceEmotionEvent('no_face_detected', 'result', 'start_camera', {
      face_count: 0,
      consecutive_no_face_count: consecutiveNoFaceCount
    });
    scheduleFaceEmotionSnapshot('start_camera', 350);
    setStatus('🔍 请将脸移近摄像头...', '#F59E0B');
  }
}

function updateEmotionUI(face) {
  const { emotion_idx, emotion_cn, scores } = face;

  document.getElementById('emotionEmoji').textContent = EMOJIS[emotion_idx] || '🤔';
  document.getElementById('emotionLabel').textContent = emotion_cn || '识别中...';

  if (scores && scores.length > 0) {
    const maxScore = Math.max(...scores);
    document.getElementById('emotionConfidence').textContent =
      `置信度: ${(maxScore * 100).toFixed(1)}%`;

    scores.forEach((score, i) => {
      const barEl = document.getElementById('bar_' + i);
      const pctEl = document.getElementById('pct_' + i);
      if (barEl && pctEl) {
        barEl.style.width = (score * 100).toFixed(1) + '%';
        pctEl.textContent = (score * 100).toFixed(1) + '%';
      }
    });
  }
}

function setStatus(msg, color) {
  const el = document.getElementById('statusMsg');
  el.textContent = msg;
  el.style.color = color;
}

// ── Capture Loop ──────────────────────────────────────────────────────────────
function startCaptureLoop() {
  if (intervalId) clearInterval(intervalId);
  intervalId = setInterval(captureAndPredict, DETECT_INTERVAL_MS);
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
});
