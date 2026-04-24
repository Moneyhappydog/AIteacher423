/*
 * 情感计算前端脚本
 *
 * 功能：
 * 1. 表情识别（摄像头）
 * 2. 声音识别（麦克风录音）
 * 3. 多策略情感计算
 * 4. 可调节权重比例
 * 5. 双模型独立选择
 */

// 全局变量
let videoStream = null;
let captureInterval = null;
let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let currentFaceResult = null;
let currentAudioResult = null;
let currentFusionResult = null;
let selectedToy = null;
let lastEmotionEventKeys = {};
let lastEmotionEventTimes = {};
let firstFaceFrame = true;  // true until first annotated image arrives
let inflightFaceCount = 0;   // 当前在飞行中的面部请求数
let latestFaceTimestamp = 0;   // 最新面部请求时间戳（用于处理乱序）
let latestFaceResponse = null; // 最新收到的面部响应

// 情绪颜色映射
const emotionColors = {
  'happy': '#FFD700',
  'sad': '#4169E1',
  'angry': '#FF4500',
  'fear': '#9400D3',
  'surprise': '#00CED1',
  'neutral': '#808080',
  'disgust': '#228B22'
};

const emotionEmojis = {
  'happy': '😊', 'sad': '😢', 'angry': '😠',
  'fear': '😨', 'surprise': '😮', 'neutral': '😐', 'disgust': '🤢'
};

const emotionCN = {
  'happy': '开心', 'sad': '难过', 'angry': '生气',
  'fear': '害怕', 'surprise': '惊讶', 'neutral': '平静', 'disgust': '厌恶'
};

// 策略中文名称
const strategyCN = {
  'weighted_average': '加权平均',
  'max_confidence': '最大置信度',
  'emotion_voting': '情绪投票',
  'adaptive': '自适应融合'
};

// ── 摄像头控制 ────────────────────────────────────────────────────────────────
function getEmotionConfidence(result) {
  if (!result) return null;
  if (typeof result.confidence === 'number') return result.confidence;
  if (result.scores && result.emotion && typeof result.scores[result.emotion] === 'number') {
    return result.scores[result.emotion];
  }
  return null;
}

function summarizeEmotionResult(result) {
  if (!result) return null;
  return {
    emotion: result.emotion || result.fused_emotion || null,
    emotion_cn: result.emotion_cn || result.fused_emotion_cn || null,
    confidence: getEmotionConfidence(result),
    model_source: result.model_source || null,
    model_name: result.model_name || null
  };
}

function getEmotionComputingSnapshot() {
  return {
    face_model_id: typeof getCurrentFaceModelId === 'function' ? getCurrentFaceModelId() : null,
    audio_model_id: typeof getCurrentAudioModelId === 'function' ? getCurrentAudioModelId() : null,
    fusion_strategy: typeof getCurrentStrategy === 'function' ? getCurrentStrategy() : 'weighted_average',
    face_weight: typeof getCurrentWeight === 'function' ? getCurrentWeight() : 0.6,
    camera_started: !!videoStream,
    recording: !!isRecording,
    selected_toy: selectedToy,
    last_face_result: summarizeEmotionResult(currentFaceResult),
    last_audio_result: summarizeEmotionResult(currentAudioResult),
    last_fusion_result: summarizeEmotionResult(currentFusionResult)
  };
}

function reportEmotionEvent(eventName, eventType, stepCode, payload) {
  const throttleMs = eventName === 'face_result_updated' || eventName === 'fusion_result_updated' ? 1500 : 0;
  const eventKey = `${eventName}:${payload && payload.emotion ? payload.emotion : ''}`;
  const lastKey = lastEmotionEventKeys[eventName];
  const lastTime = lastEmotionEventTimes[eventName] || 0;
  const now = Date.now();
  if (throttleMs && lastKey === eventKey && now - lastTime < throttleMs) {
    return Promise.resolve({ skipped: true, reason: 'throttled' });
  }
  lastEmotionEventKeys[eventName] = eventKey;
  lastEmotionEventTimes[eventName] = now;

  if (window.AiContextTracker && stepCode) {
    window.AiContextTracker.setStep(stepCode);
  }
  if (!window.AiCourseBridge) return Promise.resolve({ skipped: true });
  return window.AiCourseBridge.track(eventName, {
    eventType: eventType,
    stepCode: stepCode,
    payload: Object.assign({}, payload || {}, {
      snapshot: getEmotionComputingSnapshot()
    })
  });
}

function scheduleEmotionSnapshot(stepCode, delayMs) {
  if (window.AiContextTracker && stepCode) {
    window.AiContextTracker.setStep(stepCode);
  }
  if (window.AiContextTracker && typeof window.AiContextTracker.scheduleSnapshot === 'function') {
    window.AiContextTracker.scheduleSnapshot(delayMs || 500, { stepCode: stepCode });
  } else if (window.AiCourseBridge) {
    window.AiCourseBridge.snapshot({ stepCode: stepCode });
  }
}

window.getEmotionComputingSnapshot = getEmotionComputingSnapshot;
window.reportEmotionEvent = reportEmotionEvent;
window.scheduleEmotionSnapshot = scheduleEmotionSnapshot;

const FACE_DETECT_INTERVAL_MS = 80;  // 面部检测间隔: 80ms (~12.5 FPS)
const FACE_JPEG_QUALITY = 0.75; // JPEG压缩质量: 0.75，清晰度与传输效率平衡
const FACE_VIDEO_WIDTH = 640;  // 视频宽度: 640px（原320）
const FACE_VIDEO_HEIGHT = 480;  // 视频高度: 480px（原240）
const MAX_CONCURRENT_FACE = 2;    // 最多2个并发请求

async function startCamera() {
  try {
    videoStream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: FACE_VIDEO_WIDTH },
        height: { ideal: FACE_VIDEO_HEIGHT },
        frameRate: { ideal: 30 }
      }
    });

    const video = document.getElementById('videoEl');
    video.srcObject = videoStream;
    video.style.display = 'block';
    document.getElementById('cameraPlaceholder').style.display = 'none';
    document.getElementById('startCameraBtn').classList.add('d-none');
    document.getElementById('stopCameraBtn').classList.remove('d-none');

    // 重置并发状态
    inflightFaceCount = 0;
    latestFaceTimestamp = 0;
    latestFaceResponse = null;

    // 开始定时捕获 (100ms间隔，比原来500ms快5倍)
    captureInterval = setInterval(captureAndPredict, FACE_DETECT_INTERVAL_MS);
    reportEmotionEvent('camera_started', 'camera', 'single_modal_capture', {
      interval_ms: FACE_DETECT_INTERVAL_MS
    });
    scheduleEmotionSnapshot('single_modal_capture');

  } catch (err) {
    alert('无法打开摄像头: ' + err.message);
  }
}

function stopCamera() {
  if (videoStream) {
    videoStream.getTracks().forEach(track => track.stop());
    videoStream = null;
  }

  if (captureInterval) {
    clearInterval(captureInterval);
    captureInterval = null;
  }

  firstFaceFrame = true;
  inflightFaceCount = 0;
  latestFaceTimestamp = 0;
  latestFaceResponse = null;

  const outputImg = document.getElementById('outputImg');
  outputImg.style.opacity = '0';
  outputImg.src = '';

  document.getElementById('videoEl').style.display = 'none';
  document.getElementById('cameraPlaceholder').style.display = 'flex';
  document.getElementById('startCameraBtn').classList.remove('d-none');
  document.getElementById('stopCameraBtn').classList.add('d-none');
  reportEmotionEvent('camera_stopped', 'camera', 'single_modal_capture');
  scheduleEmotionSnapshot('single_modal_capture');
}

async function captureAndPredict() {
  // 限制并发请求数，避免请求堆积导致延迟
  if (inflightFaceCount >= MAX_CONCURRENT_FACE) return;

  const video = document.getElementById('videoEl');
  const canvas = document.getElementById('canvasEl');
  const ctx = canvas.getContext('2d');

  canvas.width = video.videoWidth || FACE_VIDEO_WIDTH;
  canvas.height = video.videoHeight || FACE_VIDEO_HEIGHT;

  // 水平翻转绘制
  ctx.translate(canvas.width, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(video, 0, 0);
  ctx.setTransform(1, 0, 0, 1, 0, 0);

  // 使用较低质量JPEG减少传输时间
  const imageData = canvas.toDataURL('image/jpeg', FACE_JPEG_QUALITY);

  // 获取当前选择的模型ID
  const faceModelId = typeof getCurrentFaceModelId === 'function' ? getCurrentFaceModelId() : null;

  const reqTimestamp = Date.now();
  inflightFaceCount++;

  try {
    const resp = await fetch('/emotion/predict_face', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: imageData, face_model_id: faceModelId })
    });

    const result = await resp.json();
    inflightFaceCount--;

    if (result.success) {
      currentFaceResult = result;

      // 只使用最新收到的响应，避免旧响应覆盖新标注（解决乱序问题）
      if (reqTimestamp >= latestFaceTimestamp) {
        latestFaceTimestamp = reqTimestamp;
        latestFaceResponse = result;
        renderFaceResult(result);
      }
    }
  } catch (err) {
    inflightFaceCount--;
    console.error('表情识别失败:', err);
  }
}

function renderFaceResult(result) {
  // 显示标注图
  if (result.image) {
    const outputImg = document.getElementById('outputImg');
    outputImg.src = result.image;
    if (firstFaceFrame) {
      outputImg.style.display = 'block';
      requestAnimationFrame(() => {
        requestAnimationFrame(() => outputImg.style.opacity = '1');
      });
      firstFaceFrame = false;
    }
  }

  displayFaceResult(result);
  updateFusion();
}

function displayFaceResult(result) {
  const container = document.getElementById('faceResult');
  const emoji = emotionEmojis[result.emotion] || '😐';
  const cn = result.emotion_cn || emotionCN[result.emotion] || result.emotion;
  const confidence = (result.scores[result.emotion] * 100).toFixed(1);

  // 获取模型来源
  const modelSource = result.model_source === 'custom'
    ? `<small style="color: #10b981;">📦 ${result.model_name || '自定义模型'}</small>`
    : `<small style="color: #7C3AED;">🤖 ${result.model_name || '系统模型'}</small>`;

  container.innerHTML = `
    <div style="font-size: 2.5rem;">${emoji}</div>
    <div class="fw-bold" style="color: #7C3AED;">${cn}</div>
    <div class="confidence-bar mt-2">
      <div class="confidence-fill" style="width: ${confidence}%"></div>
    </div>
    <small class="text-muted">置信度: ${confidence}%</small>
    <div style="margin-top: 4px;">${modelSource}</div>
  `;

  // 更新详细面板
  document.getElementById('faceDetail').innerHTML = `
    <div class="emotion-emoji">${emoji}</div>
    <div class="fw-bold">${cn}</div>
    <small class="text-muted">${confidence}%</small>
    <div style="margin-top: 4px; font-size: 0.7rem;">${modelSource}</div>
  `;
  reportEmotionEvent('face_result_updated', 'result', 'single_modal_result', {
    emotion: result.emotion,
    emotion_cn: cn,
    confidence: getEmotionConfidence(result),
    model_source: result.model_source || null,
    model_name: result.model_name || null
  });
  scheduleEmotionSnapshot('single_modal_result', 350);
}

// ── 录音控制 ────────────────────────────────────────────────────────────────
let audioStream = null;
let realtimeInterval = null;
let audioContext = null;
let analyserNode = null;
let waveformAnimationId = null;

async function toggleRecording() {
  if (!isRecording) {
    await startRecording();
  } else {
    stopRecording();
  }
}

async function startRecording() {
  try {
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(audioStream);
    audioChunks = [];

    // 实时识别：每 500ms 的片段送识别，结果实时更新右侧融合
    let segmentChunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        audioChunks.push(e.data);
        segmentChunks.push(e.data);
      }
      if (segmentChunks.length >= 1) {
        const segmentBlob = new Blob(segmentChunks, { type: 'audio/webm' });
        processAudioRealtime(segmentBlob);
        segmentChunks = [];
      }
    };

    mediaRecorder.onstop = async () => {
      stopRecordingWaveform();
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      await processAudio(audioBlob);
      if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop());
        audioStream = null;
      }
    };

    mediaRecorder.start(500); // 每 500ms 一次 ondataavailable，用于实时识别
    isRecording = true;

    document.getElementById('recordBtn').innerHTML =
      '<i class="bi bi-stop-fill"></i> 停止录音';
    document.getElementById('recordBtn').classList.remove('btn-green');
    document.getElementById('recordBtn').classList.add('btn-red');

    // 用真实麦克风音量驱动波形，录音期间持续显示
    startRecordingWaveform();
    reportEmotionEvent('recording_started', 'audio', 'single_modal_capture', {
      realtime_interval_ms: 500
    });
    scheduleEmotionSnapshot('single_modal_capture');
  } catch (err) {
    alert('无法录音: ' + err.message);
  }
}

function stopRecording() {
  if (mediaRecorder && isRecording) {
    mediaRecorder.stop();
    isRecording = false;
    document.getElementById('recordBtn').innerHTML =
      '<i class="bi bi-mic-fill"></i> 开始录音';
    document.getElementById('recordBtn').classList.add('btn-green');
    document.getElementById('recordBtn').classList.remove('btn-red');
    reportEmotionEvent('recording_stopped', 'audio', 'single_modal_capture');
    scheduleEmotionSnapshot('single_modal_capture');
  }
}

// 使用 Web Audio API 实时绘制波形（录音期间持续显示）
function startRecordingWaveform() {
  if (!audioStream) return;
  const container = document.getElementById('audioWaveform');
  container.innerHTML = '<canvas id="waveformCanvas" style="width:100%;height:100%;display:block;border-radius:8px;"></canvas>';
  const canvas = document.getElementById('waveformCanvas');
  const ctx = canvas.getContext('2d');
  const rect = container.getBoundingClientRect();
  canvas.width = Math.max(1, Math.floor(rect.width));
  canvas.height = Math.max(40, Math.floor(rect.height) || 60);

  try {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    analyserNode = audioContext.createAnalyser();
    analyserNode.fftSize = 256;
    analyserNode.smoothingTimeConstant = 0.6;
    const source = audioContext.createMediaStreamSource(audioStream);
    source.connect(analyserNode);

    const bufferLength = analyserNode.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    const barCount = 24;
    const barWidth = Math.max(4, (canvas.width / barCount) - 4);

    function draw() {
      if (!isRecording || !analyserNode) return;
      waveformAnimationId = requestAnimationFrame(draw);
      analyserNode.getByteFrequencyData(dataArray);
      ctx.fillStyle = '#f5f5f5';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      const step = Math.floor(bufferLength / barCount);
      for (let i = 0; i < barCount; i++) {
        const v = dataArray[i * step] || 0;
        const h = Math.max(4, (v / 255) * (canvas.height * 0.9));
        const x = i * (barWidth + 4);
        const y = (canvas.height - h) / 2;
        ctx.fillStyle = '#10B981';
        if (ctx.roundRect) {
          ctx.beginPath();
          ctx.roundRect(x, y, barWidth, h, 4);
          ctx.fill();
        } else {
          ctx.fillRect(x, y, barWidth, h);
        }
      }
    }
    draw();
  } catch (e) {
    console.warn('AnalyserNode 不可用，使用动画波形', e);
    showRecordingWaveFallback();
  }
}

function stopRecordingWaveform() {
  if (waveformAnimationId) {
    cancelAnimationFrame(waveformAnimationId);
    waveformAnimationId = null;
  }
  if (audioContext) {
    audioContext.close().catch(() => { });
    audioContext = null;
  }
  analyserNode = null;
}

function showRecordingWaveFallback() {
  const container = document.getElementById('audioWaveform');
  const bars = [];
  for (let i = 0; i < 20; i++) {
    bars.push(`<div style="width: 8px; height: ${20 + Math.random() * 40}px; background: #10B981; border-radius: 4px; animation: wave 0.5s ease-in-out infinite; animation-delay: ${i * 0.05}s;"></div>`);
  }
  container.innerHTML = `<div style="display: flex; align-items: center; justify-content: center; gap: 4px; height: 100%;">${bars.join('')}</div>`;
  if (!document.getElementById('waveAnimation')) {
    const style = document.createElement('style');
    style.id = 'waveAnimation';
    style.textContent = `@keyframes wave { 0%, 100% { transform: scaleY(1); } 50% { transform: scaleY(0.5); } }`;
    document.head.appendChild(style);
  }
}

// 实时处理音频片段（与表情同步：每约 500ms 更新一次声音情绪并刷新右侧融合）
async function processAudioRealtime(audioBlob) {
  if (audioBlob.size < 1000) return; // 跳过太小的片段

  // 获取当前选择的声音情绪模型ID
  const audioModelId = typeof getCurrentAudioModelId === 'function' ? getCurrentAudioModelId() : null;

  const formData = new FormData();
  formData.append('audio', audioBlob, 'segment.webm');
  if (audioModelId) {
    formData.append('audio_model_id', audioModelId);
  }

  try {
    const resp = await fetch('/emotion/predict_audio', {
      method: 'POST',
      body: formData
    });
    const result = await resp.json();
    if (result.success) {
      currentAudioResult = result;
      displayAudioResult(result, true); // 录音中：只更新结果，不清空波形
      updateFusion();
    }
  } catch (err) {
    console.error('实时识别失败:', err);
  }
}

async function processAudio(audioBlob) {
  // 获取当前选择的声音情绪模型ID
  const audioModelId = typeof getCurrentAudioModelId === 'function' ? getCurrentAudioModelId() : null;

  const formData = new FormData();
  formData.append('audio', audioBlob, 'recording.webm');
  if (audioModelId) {
    formData.append('audio_model_id', audioModelId);
  }

  document.getElementById('audioWaveform').innerHTML =
    '<p class="text-center text-muted">正在分析...</p>';

  try {
    // 使用情感计算页面的专用接口
    const resp = await fetch('/emotion/predict_audio', {
      method: 'POST',
      body: formData
    });

    const result = await resp.json();

    if (result.success) {
      currentAudioResult = result;
      displayAudioResult(result);
      updateFusion();
    } else {
      document.getElementById('audioWaveform').innerHTML =
        '<p class="text-danger">识别失败</p>';
    }
  } catch (err) {
    document.getElementById('audioWaveform').innerHTML =
      '<p class="text-danger">识别失败: ' + err.message + '</p>';
  }
}

function displayAudioResult(result, isRealtime) {
  const container = document.getElementById('audioResult');
  const emoji = emotionEmojis[result.emotion] || '😐';
  const cn = result.emotion_cn || emotionCN[result.emotion] || result.emotion;
  const confidence = (result.scores[result.emotion] * 100).toFixed(1);

  // 获取模型来源
  const modelSource = result.model_source === 'custom'
    ? `<small style="color: #10b981;">📦 ${result.model_name || '自定义模型'}</small>`
    : `<small style="color: #10B981;">🤖 ${result.model_name || '系统模型'}</small>`;

  // 录音中实时更新时保留波形，不清空；仅停止录音后的最终结果才清空波形区
  if (!isRealtime) {
    document.getElementById('audioWaveform').innerHTML = '';
  }

  container.innerHTML = `
    <div style="font-size: 2.5rem;">${emoji}</div>
    <div class="fw-bold" style="color: #10B981;">${cn}</div>
    <div class="confidence-bar mt-2">
      <div class="confidence-fill" style="width: ${confidence}%; background: linear-gradient(90deg, #10B981, #059669);"></div>
    </div>
    <small class="text-muted">置信度: ${confidence}%</small>
    <div style="margin-top: 4px;">${modelSource}</div>
  `;

  // 更新详细面板
  document.getElementById('audioDetail').innerHTML = `
    <div class="emotion-emoji">${emoji}</div>
    <div class="fw-bold">${cn}</div>
    <small class="text-muted">${confidence}%</small>
    <div style="margin-top: 4px; font-size: 0.7rem;">${modelSource}</div>
  `;
  if (!isRealtime) {
    reportEmotionEvent('audio_result_updated', 'result', 'single_modal_result', {
      emotion: result.emotion,
      emotion_cn: cn,
      confidence: getEmotionConfidence(result),
      model_source: result.model_source || null,
      model_name: result.model_name || null
    });
    scheduleEmotionSnapshot('single_modal_result', 350);
  }
}

// ── 融合分析 ────────────────────────────────────────────────────────────────
async function updateFusion() {
  if (!currentFaceResult && !currentAudioResult) {
    return;
  }

  const faceData = currentFaceResult ? {
    emotion: currentFaceResult.emotion,
    emotion_cn: currentFaceResult.emotion_cn,
    scores: currentFaceResult.scores
  } : null;

  const audioData = currentAudioResult ? {
    emotion: currentAudioResult.emotion,
    emotion_cn: currentAudioResult.emotion_cn,
    scores: currentAudioResult.scores
  } : null;

  // 获取当前配置的权重和策略
  const faceWeight = typeof getCurrentWeight === 'function' ? getCurrentWeight() : 0.6;
  const strategy = typeof getCurrentStrategy === 'function' ? getCurrentStrategy() : 'weighted_average';

  try {
    const resp = await fetch('/emotion/fuse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        face_data: faceData,
        audio_data: audioData,
        face_weight: faceWeight,
        strategy: strategy
      })
    });

    const result = await resp.json();

    if (result.success) {
      displayFusedResult(result);
    }
  } catch (err) {
    console.error('融合分析失败:', err);
  }
}

function displayFusedResult(result) {
  currentFusionResult = result;
  const container = document.getElementById('fusedEmotion');
  const emoji = emotionEmojis[result.fused_emotion] || '😐';
  const cn = result.fused_emotion_cn || emotionCN[result.fused_emotion] || result.fused_emotion;
  const confidence = (result.confidence * 100).toFixed(1);

  // 获取策略名称
  const strategyName = strategyCN[result.fusion_method] || result.fusion_method || '加权平均';

  // 根据策略确定实际使用的权重
  let facePercent, audioPercent, weightDisplay;
  if (result.fusion_method === 'adaptive' && result.adaptive_weights) {
    // 自适应策略：显示动态计算的权重
    facePercent = Math.round(result.adaptive_weights.face * 100);
    audioPercent = Math.round(result.adaptive_weights.audio * 100);
    weightDisplay = `😀${facePercent}% + 🎤${audioPercent}%`;
  } else if (result.fusion_method === 'max_confidence') {
    // 最大置信度策略：显示选中的模态来源
    const sourceMap = {
      'face': '😀 表情模型',
      'audio': '🎤 声音情绪模型'
    };
    const source = sourceMap[result.dominant_source] || '未知';
    weightDisplay = `采用${source}结果`;
  } else {
    // 加权平均和情绪投票：显示配置权重
    const weights = result.weights || { face: 0.6, audio: 0.4 };
    facePercent = Math.round(weights.face * 100);
    audioPercent = Math.round(weights.audio * 100);
    weightDisplay = `😀${facePercent}% + 🎤${audioPercent}%`;
  }

  container.innerHTML = `
    <div class="emotion-emoji">${emoji}</div>
    <div class="emotion-label">${cn}</div>
    <div class="confidence-bar mt-2" style="max-width: 300px; margin: 0 auto;">
      <div class="confidence-fill" style="width: ${confidence}%"></div>
    </div>
    <small class="text-muted">综合置信度: ${confidence}%</small>
    <div style="margin-top: 8px; font-size: 0.75rem; color: #7C3AED;">
      <span style="background: rgba(124,58,237,0.1); padding: 2px 8px; border-radius: 4px;">
        ${strategyName}
      </span>
      <span style="margin-left: 8px;">${weightDisplay}</span>
    </div>
  `;

  // 更新可视化条
  updateEmotionVisualizer(result.fused_scores);

  // 更新融合信息
  updateFusionInfo(result);

  // 更新小玩具预览
  updateToyPreview(result.fused_emotion);
  reportEmotionEvent('fusion_result_updated', 'result', 'fusion_result', {
    emotion: result.fused_emotion,
    emotion_cn: cn,
    confidence: getEmotionConfidence(result),
    fusion_method: result.fusion_method || null,
    dominant_source: result.dominant_source || null,
    weights: result.weights || result.adaptive_weights || null
  });
  scheduleEmotionSnapshot('fusion_result', 350);
}

function updateFusionInfo(result) {
  const infoText = document.getElementById('fusionInfoText');
  if (!infoText) return;

  const strategyName = strategyCN[result.fusion_method] || result.fusion_method || '加权平均';
  const weights = result.weights || { face: 0.6, audio: 0.4 };
  const facePercent = Math.round(weights.face * 100);
  const audioPercent = Math.round(weights.audio * 100);

  let info = '';

  // 根据策略显示不同信息
  if (result.fusion_method === 'adaptive' && result.adaptive_weights) {
    // 自适应策略显示动态计算的权重
    const adFace = Math.round(result.adaptive_weights.face * 100);
    const adAudio = Math.round(result.adaptive_weights.audio * 100);
    info = `<strong>${strategyName}</strong> | ` +
      `表情 <strong>${adFace}%</strong> + 声音 <strong>${adAudio}%</strong>` +
      `<br><small style="color: #10b981;">系统根据识别质量自动调整权重</small>`;
  } else if (result.fusion_method === 'max_confidence') {
    // 最大置信度策略
    const sourceMap = {
      'face': '😀 表情模型',
      'audio': '🎤 声音情绪模型'
    };
    const source = sourceMap[result.dominant_source] || '未知';
    info = `<strong>${strategyName}</strong> | 采用 <strong>${source}</strong> 的结果<br><small style="color: #7C3AED;">（选择置信度更高的模态作为最终结果）</small>`;
  } else {
    // 加权平均和情绪投票
    info = `<strong>${strategyName}</strong> | ` +
      `表情 <strong>${facePercent}%</strong> + 声音 <strong>${audioPercent}%</strong>`;
  }

  infoText.innerHTML = info;
}

function updateEmotionVisualizer(scores) {
  const container = document.getElementById('emotionVisualizer');
  const emotions = ['happy', 'sad', 'angry', 'fear', 'surprise', 'neutral', 'disgust'];

  let html = '';
  emotions.forEach(emotion => {
    const height = (scores[emotion] || 0) * 70 + 10;
    const color = emotionColors[emotion] || '#999';
    html += `<div class="emotion-bar" style="height: ${height}px; background: ${color};"></div>`;
  });

  container.innerHTML = html;
}

// ── 小玩具选择 ────────────────────────────────────────────────────────────────
function selectToy(toy) {
  selectedToy = toy;

  document.querySelectorAll('.toy-option').forEach(opt => {
    opt.classList.remove('selected');
    if (opt.dataset.toy === toy) {
      opt.classList.add('selected');
    }
  });

  document.getElementById('toyPreview').style.display = 'block';

  // 获取当前情绪
  const fused = document.getElementById('fusedEmotion');
  const label = fused.querySelector('.emotion-label');
  const emotion = Object.keys(emotionCN).find(key => emotionCN[key] === label?.textContent) || 'happy';

  updateToyPreview(emotion);
  reportEmotionEvent('toy_selected', 'feedback', 'toy_feedback', {
    selected_toy: toy,
    emotion: emotion
  });
  scheduleEmotionSnapshot('toy_feedback');
}

function updateToyPreview(emotion) {
  const color = emotionColors[emotion] || '#999';
  const emoji = emotionEmojis[emotion] || '😐';

  document.getElementById('lampPreview').classList.add('d-none');
  document.getElementById('diaryPreview').classList.add('d-none');
  document.getElementById('badgePreview').classList.add('d-none');

  if (selectedToy === 'lamp') {
    document.getElementById('lampPreview').classList.remove('d-none');
    document.querySelector('.preview-light').style.background = color;
    document.querySelector('.preview-light').style.color = color;
  } else if (selectedToy === 'diary') {
    document.getElementById('diaryPreview').classList.remove('d-none');
    document.getElementById('diaryContent').textContent = `今日心情: ${emotionCN[emotion] || emotion}`;
  } else if (selectedToy === 'badge') {
    document.getElementById('badgePreview').classList.remove('d-none');
    document.getElementById('badgeEmoji').textContent = emoji;
  }
}

// ── 初始化 ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // 初始化情绪可视化
  updateEmotionVisualizer({
    happy: 0.14, sad: 0.14, angry: 0.14, fear: 0.14,
    surprise: 0.14, neutral: 0.14, disgust: 0.14
  });
});
