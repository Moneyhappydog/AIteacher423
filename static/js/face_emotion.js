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

// ── Camera ──────────────────────────────────────────────────────────────────
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
      };
    })
    .catch(err => {
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
    updateEmotionUI(face);
    setStatus('✅ 检测成功！', '#10B981');
  } else {
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
