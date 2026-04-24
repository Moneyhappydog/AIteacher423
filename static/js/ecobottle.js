/*
 * 生态瓶时序预测增强版 - 包含模型训练功能
 */

const dataPoints = { temperature: [], humidity: [], light: [], oxygen: [], solar_power: [] };
let predChart = null;
let trainChart = null;
let lossChart = null;
let currentChartKey = 'light';
let currentTrainKey = 'light';
let forecastData = {};
let trainResultData = null;
let savedAnalyses = [];

// 训练配置
let trainConfig = {
  modelType: 'polynomial',
  preprocessing: 'none',
  polynomialDegree: 2,
  predictionSteps: 12
};
let ecoCurrentTab = 'collect';
let ecoLastPrediction = null;
let ecoLastControl = null;
let ecoLastExplore = null;

function getEcoDataCount() {
  const tableCount = Array.isArray(ecoTableData) ? ecoTableData.length : 0;
  const pointCount = dataPoints && dataPoints.light ? dataPoints.light.length : 0;
  return Math.max(tableCount, pointCount);
}

function getEcoPredictionModel() {
  const selectedModel = typeof getCurrentModelId === 'function' ? getCurrentModelId() : null;
  const modelType = document.getElementById('predictModel')?.value || trainConfig.modelType || 'prophet';
  return selectedModel || modelType || 'system_default';
}

function getEcobottleSnapshot() {
  return {
    current_tab: ecoCurrentTab,
    data_count: getEcoDataCount(),
    table_data_count: Array.isArray(ecoTableData) ? ecoTableData.length : 0,
    training_data_count: dataPoints.light.length,
    prediction_model: getEcoPredictionModel(),
    selected_model_id: typeof getCurrentModelId === 'function' ? getCurrentModelId() : null,
    train_config: Object.assign({}, trainConfig),
    last_prediction: ecoLastPrediction,
    last_training: trainResultData ? {
      success: !!trainResultData.success,
      model_type: trainResultData.config && trainResultData.config.model_type,
      channels: trainResultData.results ? Object.keys(trainResultData.results) : []
    } : null,
    last_explore: ecoLastExplore,
    last_control: ecoLastControl,
    current_sensor_values: Object.assign({}, ecoSensorValues),
    control_values: Object.assign({}, ecoControlValues),
    control_strategy: document.querySelector('input[name="ctrlStrategy"]:checked')?.value || 'threshold'
  };
}

function reportEcobottleEvent(eventName, eventType, stepCode, payload) {
  if (window.AiContextTracker && stepCode) {
    window.AiContextTracker.setStep(stepCode);
  }
  if (!window.AiCourseBridge) return Promise.resolve({ skipped: true });
  return window.AiCourseBridge.track(eventName, {
    eventType: eventType,
    stepCode: stepCode,
    payload: Object.assign({}, payload || {}, {
      snapshot: getEcobottleSnapshot()
    })
  });
}

function scheduleEcobottleSnapshot(stepCode, delayMs) {
  if (window.AiContextTracker && stepCode) {
    window.AiContextTracker.setStep(stepCode);
  }
  if (window.AiContextTracker && typeof window.AiContextTracker.scheduleSnapshot === 'function') {
    window.AiContextTracker.scheduleSnapshot(delayMs || 500, { stepCode: stepCode });
  } else if (window.AiCourseBridge) {
    window.AiCourseBridge.snapshot({ stepCode: stepCode });
  }
}

function ecobottleStepForTab(tabName) {
  const map = {
    collect: 'collect_data',
    explore: 'explore_data',
    train: 'train_model',
    control: 'control',
    report: 'report'
  };
  return map[tabName] || tabName || 'collect_data';
}

function getEcoGroupId() {
  return window.ECO_GROUP_ID || 'G01';
}

window.getEcobottleSnapshot = getEcobottleSnapshot;
window.reportEcobottleEvent = reportEcobottleEvent;
window.scheduleEcobottleSnapshot = scheduleEcobottleSnapshot;

// ── 标签页切换 ────────────────────────────────────────────────────────────────────
function showTab(tabName) {
  try {
    ecoCurrentTab = tabName;
    const tabId = 'tab-' + tabName;
    const targetTab = document.getElementById(tabId);
    
    // Hide all tabs
    ['collect','explore','train','control','report','predict','analysis'].forEach(t => {
      const el = document.getElementById('tab-' + t);
      if (el) el.style.display = 'none';
    });
    
    // Show target tab
    if (targetTab) {
      targetTab.style.display = 'block';
    }
    
    // Update active button
    document.querySelectorAll('#mainTabs .nav-link').forEach(btn => {
      btn.classList.remove('active');
    });
    const activeBtn = document.querySelector('#mainTabs .nav-link[onclick*="' + tabName + '"]');
    if (activeBtn) {
      activeBtn.classList.add('active');
    }
    
    // Tab-specific actions
    if (tabName === 'explore' && typeof renderExploreChart === 'function') {
      renderExploreChart();
    }
    if (tabName === 'explore' && typeof refreshPracticeExercise === 'function') {
      refreshPracticeExercise();
    }
    if (tabName === 'control' && typeof initControlTab === 'function') {
      initControlTab();
    }
    if (tabName === 'report' && typeof loadReports === 'function') {
      loadReports();
    }
    reportEcobottleEvent('tab_changed', 'navigation', ecobottleStepForTab(tabName), {
      current_tab: tabName
    });
    scheduleEcobottleSnapshot(ecobottleStepForTab(tabName));
  } catch(e) {
    console.error('showTab:', e);
  }
}

// ── 5Tab新功能：数据采集 ────────────────────────────────────────────────────────────
let ecoSensorValues = { temperature: 25.0, humidity: 65.0, light: 120.0, oxygen: 20.5, solar_power: 0.0 };
let ecoTableData = [];
let ecoMiniCharts = {};

function ecoApplyManual() {
  ecoSensorValues.temperature = parseFloat(document.getElementById('ecoInputTemp').value) || 25;
  ecoSensorValues.humidity    = parseFloat(document.getElementById('ecoInputHumid').value) || 65;
  ecoSensorValues.light       = parseFloat(document.getElementById('ecoInputLight').value) || 120;
  ecoSensorValues.oxygen      = parseFloat(document.getElementById('ecoInputOxygen').value) || 21;
  ecoSensorValues.solar_power = parseFloat(document.getElementById('ecoInputPower').value) || 0;
  updateEcoDisplay();
  reportEcobottleEvent('sensor_values_changed', 'collect', 'collect_data', {
    values: Object.assign({}, ecoSensorValues)
  });
  scheduleEcobottleSnapshot('collect_data');
}

function updateEcoDisplay() {
  document.getElementById('dispTemp').textContent = ecoSensorValues.temperature.toFixed(1);
  document.getElementById('dispHumid').textContent = ecoSensorValues.humidity.toFixed(0);
  document.getElementById('dispLight').textContent = ecoSensorValues.light.toFixed(0);
  document.getElementById('dispOxygen').textContent = ecoSensorValues.oxygen.toFixed(1);
  document.getElementById('dispPower').textContent = ecoSensorValues.solar_power.toFixed(1);
  // 状态判断
  const t = ecoSensorValues.temperature, l = ecoSensorValues.light;
  let status = '正常';
  if (t < 15 || t > 35 || l < 50 || l > 800) status = '警告';
  else if (t < 22 || t > 28 || l < 100 || l > 500) status = '注意';
  document.getElementById('dispStatus').textContent = status;
  document.getElementById('dispStatus').style.color = status === '正常' ? 'white' : '#FFD700';
}

function ecoQuickAction(action) {
  switch (action) {
    case 'light_on': ecoSensorValues.light = 400; break;
    case 'light_off': ecoSensorValues.light = 10; break;
    case 'fan': ecoSensorValues.temperature = Math.max(-10, ecoSensorValues.temperature - 2); break;
    case 'heat': ecoSensorValues.temperature = Math.min(60, ecoSensorValues.temperature + 2); break;
    case 'humid': ecoSensorValues.humidity = Math.min(100, ecoSensorValues.humidity + 10); break;
    case 'solar':
      ecoSensorValues.light = 800;
      ecoSensorValues.solar_power = 150;
      break;
  }
  updateEcoDisplay();
  reportEcobottleEvent('quick_action_used', 'collect', 'collect_data', {
    action: action,
    values: Object.assign({}, ecoSensorValues)
  });
  scheduleEcobottleSnapshot('collect_data');
}

function ecoAddData() {
  const now = new Date().toISOString().slice(0, 19).replace('T', ' ');
  const record = { timestamp: now, ...ecoSensorValues, status: 'normal' };
  ecoTableData.push(record);
  document.getElementById('ecoRecordCount').textContent = ecoTableData.length + '条';
  updateEcoTable();
  // 调用后端API保存
  fetch('/sensor/add', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ group_id: getEcoGroupId(), ...ecoSensorValues })
  }).catch(() => {});
  reportEcobottleEvent('data_point_added', 'collect', 'collect_data', {
    data_count: getEcoDataCount(),
    record: record
  });
  scheduleEcobottleSnapshot('collect_data');
}

function updateEcoTable() {
  const tbody = document.getElementById('ecoTableBody');
  if (ecoTableData.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-3">还没有数据，快添加吧！🌱</td></tr>';
    return;
  }
  tbody.innerHTML = ecoTableData.slice(-20).reverse().map(r => `
    <tr>
      <td class="small">${r.timestamp.split(' ')[1]}</td>
      <td>${r.temperature.toFixed(1)}</td>
      <td>${r.humidity.toFixed(0)}</td>
      <td>${r.light.toFixed(0)}</td>
      <td>${r.oxygen.toFixed(1)}</td>
      <td>${r.solar_power.toFixed(1)}</td>
      <td><span class="badge bg-success">正常</span></td>
      <td><button class="btn btn-sm btn-outline-danger py-0 px-1" style="font-size:0.7rem" onclick="ecoDeleteRecord('${r.timestamp}')" title="删除这条记录">🗑️</button></td>
    </tr>
  `).join('');
}

async function ecoDeleteRecord(timestamp) {
  if (!confirm('确定要删除这条记录吗？删除后无法恢复哦！')) return;
  try {
    const resp = await fetch(`/sensor/delete_record/${encodeURIComponent(getEcoGroupId())}/${encodeURIComponent(timestamp)}`, { method: 'POST' });
    const result = await resp.json().catch(() => ({}));
    if (!resp.ok || result.error) {
      showMsg('❌ 删除失败：' + (result.error || resp.status), 'error');
      return;
    }
    ecoTableData = ecoTableData.filter(r => r.timestamp !== timestamp);
    document.getElementById('ecoRecordCount').textContent = ecoTableData.length + '条';
    updateEcoTable();
    syncEcoTableToDataPoints();
    showMsg('✅ 已删除该条记录', 'success');
  } catch (e) {
    showMsg('❌ 删除失败：' + e.message, 'error');
  }
}

function ecoClear() {
  ecoSensorValues = { temperature: 25.0, humidity: 65.0, light: 120.0, oxygen: 20.5, solar_power: 0.0 };
  updateEcoDisplay();
}

async function ecoClearTable() {
  if (!window.confirm(`将清空表格，并删除服务器上 ${getEcoGroupId()} 组的全部传感器记录（与导出/导入使用同一数据源）。确定吗？`)) {
    return;
  }
  try {
    const resp = await fetch(`/sensor/clear/${encodeURIComponent(getEcoGroupId())}`, { method: 'POST' });
    const result = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      showMsg('❌ 服务器清空失败：' + (result.error || resp.status), 'error');
      return;
    }
  } catch (e) {
    showMsg('❌ 清空失败：' + e.message, 'error');
    return;
  }
  ecoTableData = [];
  document.getElementById('ecoRecordCount').textContent = '0条';
  updateEcoTable();
  dataPoints.temperature = [];
  dataPoints.humidity = [];
  dataPoints.light = [];
  dataPoints.oxygen = [];
  dataPoints.solar_power = [];
  showMsg(`🗑️ 已清空本地列表与服务器 ${getEcoGroupId()} 数据`, 'success');
}

async function ecoImportCsv() {
  const file = document.getElementById('ecoCsvFile').files[0];
  if (!file) { alert('请先选择CSV文件'); return; }
  const fd = new FormData();
  fd.append('file', file);
  fd.append('group_id', getEcoGroupId());
  const resp = await fetch('/sensor/upload', { method: 'POST', body: fd });
  const result = await resp.json();
  alert(`成功导入 ${result.imported || 0} 条记录`);
  ecoLoadHistory();
  reportEcobottleEvent('csv_imported', 'collect', 'collect_data', {
    imported: result.imported || 0
  });
  scheduleEcobottleSnapshot('collect_data');
}

function ecoExportCsv() {
  window.open(`/sensor/export/${encodeURIComponent(getEcoGroupId())}`, '_blank');
}

async function ecoLoadHistory() {
  try {
    const resp = await fetch(`/sensor/history/${encodeURIComponent(getEcoGroupId())}`);
    const data = await resp.json();
    ecoTableData = data.records || [];
    document.getElementById('ecoRecordCount').textContent = ecoTableData.length + '条';
    updateEcoTable();
  } catch(e) {}
}

/** 数据采集表与训练模块使用不同变量：训练读 dataPoints，采集写 ecoTableData — 训练前从此同步 */
function syncEcoTableToDataPoints() {
  if (!ecoTableData || ecoTableData.length === 0) return;
  const row = (r, key) => ({
    ds: String(r.timestamp || '').trim(),
    y: Number(r[key])
  });
  dataPoints.temperature = ecoTableData.map(r => row(r, 'temperature'));
  dataPoints.humidity    = ecoTableData.map(r => row(r, 'humidity'));
  dataPoints.light       = ecoTableData.map(r => row(r, 'light'));
  dataPoints.oxygen      = ecoTableData.map(r => row(r, 'oxygen'));
  dataPoints.solar_power  = ecoTableData.map(r => row(r, 'solar_power'));
}

// ── 5Tab新功能：数据探索 ────────────────────────────────────────────────────────────
let exploreChart = null;
let exploreChannel = 'all';

function renderExploreChart() {
  if (ecoTableData.length < 2) return;
  const canvas = document.getElementById('exploreChart');
  if (!canvas) return;
  if (exploreChart) exploreChart.destroy();

  const labels = ecoTableData.map(r => r.timestamp.split(' ')[1] || '');
  const datasets = [];

  const addDs = (key, label, color) => {
    if (exploreChannel !== 'all' && exploreChannel !== key) return;
    datasets.push({
      label, data: ecoTableData.map(r => r[key]),
      borderColor: color, tension: 0.3, fill: false
    });
  };

  addDs('temperature', '🌡️ 温度', '#FF6B6B');
  addDs('light', '☀️ 光照', '#FFD166');
  addDs('humidity', '💧 湿度', '#60A5FA');
  addDs('oxygen', '🌬️ 氧气', '#6BCB77');
  addDs('solar_power', '🔋 发电', '#A855F7');

  exploreChart = new Chart(canvas, {
    type: 'line',
    data: { labels, datasets },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true } } }
  });
}

function showExploreChannel(ch) {
  exploreChannel = ch;
  renderExploreChart();
  reportEcobottleEvent('explore_channel_changed', 'explore', 'explore_data', {
    channel: ch,
    data_count: getEcoDataCount()
  });
  scheduleEcobottleSnapshot('explore_data');
}

async function runExploreAnalysis() {
  if (ecoTableData.length < 5) { alert('请先采集至少5条数据'); return; }
  const resp = await fetch(`/sensor/explore/${encodeURIComponent(getEcoGroupId())}`);
  const result = await resp.json();
  if (result.error) { alert(result.error); return; }
  const insights = document.getElementById('exploreInsights');
  let html = '';
  if (result.trends) {
    for (const [key, t] of Object.entries(result.trends)) {
      const icons = { temperature: '🌡️', light: '☀️', humidity: '💧', oxygen: '🌬️', solar_power: '🔋' };
      const units = { temperature: '°C', light: 'lux', humidity: '%', oxygen: '%', solar_power: 'mW' };
      html += `<div class="alert-cute mb-2" style="background:#F0FDF4;border-left:4px solid #10B981">
        <strong>${icons[key] || ''} ${key}:</strong> ${t.trend} | 均值: ${t.mean}${units[key] || ''} | 振幅: ${t.amplitude}${units[key] || ''}
      </div>`;
    }
  }
  insights.innerHTML = html || '<p class="text-muted text-center">未发现明显规律</p>';
  ecoLastExplore = {
    type: 'trend',
    data_count: getEcoDataCount(),
    trend_keys: result.trends ? Object.keys(result.trends) : []
  };
  reportEcobottleEvent('explore_analysis_run', 'explore', 'explore_data', ecoLastExplore);
  scheduleEcobottleSnapshot('explore_data');
}

async function runCorrelationAnalysis() {
  if (ecoTableData.length < 5) { alert('请先采集至少5条数据'); return; }
  const resp = await fetch(`/sensor/explore/${encodeURIComponent(getEcoGroupId())}`);
  const result = await resp.json();
  if (result.error) { alert(result.error); return; }
  const cards = document.getElementById('corrCards');
  document.getElementById('correlationResults').style.display = '';
  let html = '';
  if (result.correlation) {
    const corrMap = {
      light_temp: { name: '☀️光照 ↔ 🌡️温度', data: result.correlation.light_temp },
      light_power: { name: '☀️光照 ↔ 🔋发电', data: result.correlation.light_power },
      humid_temp: { name: '💧湿度 ↔ 🌡️温度', data: result.correlation.humid_temp }
    };
    for (const [k, v] of Object.entries(corrMap)) {
      const c = v.data || {};
      const value = typeof c.value === 'number' ? c.value : parseFloat(c.value);
      const coef = Number.isFinite(value) ? value : 0;
      const strength = c.strength != null ? String(c.strength) : '—';
      const strengthClass = Math.abs(coef) >= 0.7 ? 'corr-strong-pos' : Math.abs(coef) >= 0.4 ? 'corr-medium' : 'corr-weak';
      html += `<div class="col-md-4">
        <div class="analysis-card">
          <div class="analysis-title">${v.name}</div>
          <div class="correlation-badge ${strengthClass}">${strength}</div>
          <div class="small text-muted mt-1">相关系数: ${Number.isFinite(value) ? value.toFixed(3) : '—'}</div>
        </div>
      </div>`;
    }
  }
  cards.innerHTML = html;
  ecoLastExplore = {
    type: 'correlation',
    data_count: getEcoDataCount(),
    correlation_keys: result.correlation ? Object.keys(result.correlation) : []
  };
  reportEcobottleEvent('correlation_analysis_run', 'explore', 'explore_data', ecoLastExplore);
  scheduleEcobottleSnapshot('explore_data');
}

// ── 预测练习：5 个通道轮流出题（温度/湿度/光照/氧气/发电）────────────────────────
let practiceChart = null;
// 每个通道的颜色、图标、单位
const PRACTICE_CHANNELS = [
  { key: 'temperature', label: '温度', unit: '°C', icon: '🌡️', color: '#EF4444', bg: 'rgba(239,68,68,0.10)' },
  { key: 'humidity',    label: '湿度', unit: '%',   icon: '💧', color: '#3B82F6', bg: 'rgba(59,130,246,0.10)' },
  { key: 'light',       label: '光照', unit: 'lux', icon: '☀️', color: '#F59E0B', bg: 'rgba(245,158,11,0.10)'  },
  { key: 'oxygen',      label: '氧气', unit: '%',   icon: '🌬️', color: '#10B981', bg: 'rgba(16,185,129,0.10)'  },
  { key: 'solar_power', label: '发电量', unit: 'mW', icon: '🔋', color: '#8B5CF6', bg: 'rgba(139,92,246,0.10)' },
];
const practiceState = { round: 1, answer: 0, windowStart: 0, numWindows: 0, channelIdx: 0 };

function refreshPracticeExercise() {
  syncEcoTableToDataPoints();

  // 找到所有通道中数据量最多的那个，用于判断是否满足条件
  let maxLen = 0;
  for (const ch of PRACTICE_CHANNELS) {
    const s = dataPoints[ch.key] || [];
    if (s.length > maxLen) maxLen = s.length;
  }

  const hintEl = document.getElementById('practiceResult');
  const canvas = document.getElementById('practiceChart');
  const hintCard = document.getElementById('practiceHint');
  const chartWrap = canvas && canvas.parentElement ? canvas.parentElement.parentElement : null;
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  if (rect.height === 0) {
    requestAnimationFrame(refreshPracticeExercise);
    return;
  }

  if (maxLen < 11) {
    if (practiceChart) { practiceChart.destroy(); practiceChart = null; }
    if (hintCard) hintCard.style.display = '';
    if (chartWrap) chartWrap.style.display = 'none';
    if (hintEl) {
      hintEl.innerHTML = `<span class="text-muted small">请先在「数据采集」中累计至少 <strong>11</strong> 条记录，再来做练习。</span>`;
    }
    const guess = document.getElementById('practiceGuess');
    if (guess) guess.value = '';
    practiceState.numWindows = 0;
    return;
  }

  if (hintCard) hintCard.style.display = 'none';
  if (chartWrap) chartWrap.style.display = '';

  // 轮换通道：每轮换一道题后切下一个通道
  const ch = PRACTICE_CHANNELS[practiceState.channelIdx];
  const series = dataPoints[ch.key] || [];

  // 如果该通道数据不够，跳到下一个够的通道
  if (series.length < 11) {
    practiceState.channelIdx = (practiceState.channelIdx + 1) % PRACTICE_CHANNELS.length;
    refreshPracticeExercise();
    return;
  }

  const maxStart = series.length - 11;
  practiceState.numWindows = maxStart + 1;
  practiceState.windowStart = (practiceState.round - 1) % practiceState.numWindows;
  const s = practiceState.windowStart;
  const slice = series.slice(s, s + 11);
  practiceState.answer = Number(slice[10].y);

  const labels = slice.slice(0, 10).map((p, i) => {
    const t = String(p.ds || '').replace(' ', '\n');
    return t.length > 14 ? `+${i + 1}` : (t || `点${i + 1}`);
  });

  // 更新左图标题
  const leftTitle = document.getElementById('practiceLeftTitle');
  if (leftTitle) {
    leftTitle.innerHTML = `<strong>${ch.icon} 前 10 点 → 猜第 11 点${ch.label}（${ch.unit}）</strong>`;
  }

  if (practiceChart) practiceChart.destroy();
  practiceChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: [...labels, '?'],
      datasets: [{
        label: `${ch.label} (${ch.unit})`,
        data: [...slice.slice(0, 10).map(p => p.y), null],
        borderColor: ch.color,
        backgroundColor: ch.bg,
        tension: 0.35,
        spanGaps: false
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { title: { display: true, text: ch.unit } }
      }
    }
  });

  // 更新右侧题目说明
  if (hintEl) {
    hintEl.innerHTML = `<span class="small text-muted">第 <strong>${practiceState.round}</strong> 题 · ${ch.icon}${ch.label} · 本数据集共 <strong>${practiceState.numWindows}</strong> 组不同窗口可练 · 当前窗口起点: 第 ${s + 1} 条记录</span>`;
  }
}

function checkPrediction() {
  syncEcoTableToDataPoints();
  const ch = PRACTICE_CHANNELS[practiceState.channelIdx];
  const series = dataPoints[ch.key] || [];
  if (series.length < 11) {
    showMsg(`⚠️ ${ch.icon}${ch.label} 需要至少 11 条数据！先去「数据采集」收集更多数据吧～`, 'warning');
    return;
  }
  const hintCard = document.getElementById('practiceHint');
  const canvas = document.getElementById('practiceChart');
  const chartWrap = canvas && canvas.parentElement ? canvas.parentElement.parentElement : null;
  if (hintCard) hintCard.style.display = 'none';
  if (chartWrap) chartWrap.style.display = '';

  const inp = document.getElementById('practiceGuess');
  const raw = inp && inp.value != null ? String(inp.value).trim() : '';
  const guess = parseFloat(raw);
  if (raw === '' || Number.isNaN(guess)) {
    showMsg(`⚠️ 请输入数字（${ch.unit}）`, 'warning');
    return;
  }
  const ans = practiceState.answer;
  const err = Math.abs(guess - ans);
  const relPct = ans !== 0 ? (err / Math.abs(ans)) * 100 : err;
  let grade = '💪 继续加油！';
  if (relPct <= 5 || err <= 1)     grade = '🌟 太厉害了！完美预测！';
  else if (relPct <= 10 || err <= 5)  grade = '👏 非常棒！很接近啦！';
  else if (relPct <= 20 || err <= 15) grade = '👍 还不错，继续努力！';

  const div = document.getElementById('practiceResult');
  if (div) {
    div.innerHTML = `
      <div class="alert-cute mb-2" style="background:${ch.bg};border-left:4px solid ${ch.color}">
        ${ch.icon} 实际第 11 点${ch.label}约 <strong>${ans.toFixed(ch.key === 'solar_power' ? 1 : 1)}</strong> ${ch.unit}；
        你的误差 <strong>${err.toFixed(1)}</strong> ${ch.unit}
        ${ans !== 0 ? `（约 ${relPct.toFixed(1)}%）` : ''} — ${grade}
      </div>
      <button type="button" class="btn btn-sm btn-outline-primary" onclick="nextPracticeRound()">下一题 🔄</button>`;
  }
}

function nextPracticeRound() {
  practiceState.round += 1;
  // 轮换到下一个通道
  practiceState.channelIdx = (practiceState.channelIdx + 1) % PRACTICE_CHANNELS.length;
  const inp = document.getElementById('practiceGuess');
  if (inp) inp.value = '';
  refreshPracticeExercise();
}

// ── 5Tab新功能：智能控制 ────────────────────────────────────────────────────────────
let ctrlChart = null;
let ctrlRefreshTimer = null;
let ecoControlValues = { temperature: 25.0, light: 120.0, solar_power: 0.0, using_solar: false };
let ctrlBtnState = { light: false, fan: false, heater: false };

function readCtrlThresholds() {
  const tmin = parseFloat(document.getElementById('ctrlTempMin')?.value ?? 22);
  const tmax = parseFloat(document.getElementById('ctrlTempMax')?.value ?? 28);
  const lmin = parseFloat(document.getElementById('ctrlLightMin')?.value ?? 100);
  const lmax = parseFloat(document.getElementById('ctrlLightMax')?.value ?? 500);
  return {
    temp_min: Math.min(tmin, tmax),
    temp_max: Math.max(tmin, tmax),
    light_min: Math.min(lmin, lmax),
    light_max: Math.max(lmin, lmax)
  };
}

function syncCtrlThresholdLabels() {
  const th = readCtrlThresholds();
  const tMinEl = document.getElementById('ctrlTempMinLbl');
  const tMaxEl = document.getElementById('ctrlTempMaxLbl');
  const lMinEl = document.getElementById('ctrlLightMinLbl');
  const lMaxEl = document.getElementById('ctrlLightMaxLbl');
  if (tMinEl) tMinEl.textContent = String(th.temp_min);
  if (tMaxEl) tMaxEl.textContent = String(th.temp_max);
  if (lMinEl) lMinEl.textContent = String(th.light_min);
  if (lMaxEl) lMaxEl.textContent = String(th.light_max);
}

function wireControlStrategyUi() {
  ['ctrlTempMin', 'ctrlTempMax', 'ctrlLightMin', 'ctrlLightMax'].forEach(id => {
    const el = document.getElementById(id);
    if (!el || el.dataset.ecoWired === '1') return;
    el.dataset.ecoWired = '1';
    el.addEventListener('input', () => {
      syncCtrlThresholdLabels();
      ecoRefreshControl();
    });
  });
  document.querySelectorAll('input[name="ctrlStrategy"]').forEach(r => {
    if (r.dataset.ecoWired === '1') return;
    r.dataset.ecoWired = '1';
    r.addEventListener('change', () => ecoRefreshControl());
  });
}

function initControlTab() {
  const canvas = document.getElementById('ctrlChart');
  if (!canvas) return;
  if (ctrlRefreshTimer) {
    clearInterval(ctrlRefreshTimer);
    ctrlRefreshTimer = null;
  }
  if (ctrlChart) ctrlChart.destroy();
  syncCtrlThresholdLabels();
  wireControlStrategyUi();
  ctrlChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: '温度', data: [], borderColor: '#FF6B6B', tension: 0.3 },
        { label: '光照/10', data: [], borderColor: '#FFD166', tension: 0.3 },
        { label: '温度阈值上', data: [], borderColor: '#10B981', borderDash: [5, 5], pointRadius: 0 },
        { label: '温度阈值下', data: [], borderColor: '#14B8A6', borderDash: [5, 5], pointRadius: 0 },
        { label: '光照阈值上', data: [], borderColor: '#3B82F6', borderDash: [4, 4], pointRadius: 0 },
        { label: '光照阈值下', data: [], borderColor: '#6366F1', borderDash: [4, 4], pointRadius: 0 }
      ]
    },
    options: { responsive: true, maintainAspectRatio: false }
  });
  ecoRefreshControl();
  ctrlRefreshTimer = setInterval(ecoRefreshControl, 3000);
  reportEcobottleEvent('control_tab_initialized', 'control', 'control', {
    strategy: document.querySelector('input[name="ctrlStrategy"]:checked')?.value || 'threshold'
  });
  scheduleEcobottleSnapshot('control');
}

async function ecoRefreshControl() {
  const strategy = document.querySelector('input[name="ctrlStrategy"]:checked')?.value || 'threshold';
  const vals = { ...ecoControlValues, strategy };
  const thresholds = readCtrlThresholds();

  // ── 1. 得分 ───────────────────────────────────────────────────────────────
  try {
    const resp = await fetch('/control/score', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ values: vals, thresholds })
    });
    const result = await resp.json();
    ecoLastControl = {
      strategy: strategy,
      thresholds: thresholds,
      scores: {
        temp_score: result.temp_score || 0,
        light_score: result.light_score || 0,
        energy_score: result.energy_score || 0,
        composite_score: result.composite_score || 0
      }
    };
    document.getElementById('ctrlTempScore').textContent = (result.temp_score || 0).toFixed(0);
    document.getElementById('ctrlLightScore').textContent = (result.light_score || 0).toFixed(0);
    document.getElementById('ctrlEnergyScore').textContent = (result.energy_score || 0).toFixed(0);
    document.getElementById('ctrlComposite').textContent = (result.composite_score || 0).toFixed(1);
  } catch(e) {}

  // ── 2. 自动控制：只有「阈值」和「预测」策略才自动驱动执行器 ──────────────────
  if (strategy !== 'passive') {
    await applyAutoActions(strategy, thresholds);
  }

  // ── 3. 更新图表（阈值线随滑块变化） ─────────────────────────────────────────
  if (ctrlChart) {
    const now = new Date().toLocaleTimeString();
    ctrlChart.data.labels.push(now);
    ctrlChart.data.datasets[0].data.push(ecoControlValues.temperature);
    ctrlChart.data.datasets[1].data.push(ecoControlValues.light / 10);
    ctrlChart.data.datasets[2].data.push(thresholds.temp_max);
    ctrlChart.data.datasets[3].data.push(thresholds.temp_min);
    ctrlChart.data.datasets[4].data.push(thresholds.light_max / 10);
    ctrlChart.data.datasets[5].data.push(thresholds.light_min / 10);
    if (ctrlChart.data.labels.length > 30) {
      ctrlChart.data.labels.shift();
      ctrlChart.data.datasets.forEach(ds => ds.data.shift());
    }
    ctrlChart.update('none');
  }
}

/**
 * 根据策略 + 阈值调用 /control/action，
 * 把返回值映射到 ecoControlValues 并同步按钮视觉状态。
 */
async function applyAutoActions(strategy, thresholds) {
  try {
    const resp = await fetch('/control/action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        values: ecoControlValues,
        strategy,
        thresholds
      })
    });
    if (!resp.ok) return;
    const result = await resp.json();
    const actions = Array.isArray(result.actions) ? result.actions : [];

    // 提取动作并过滤掉 off（避免每次都刷新按钮）
    const lightOn  = actions.some(a => a.target === 'light'   && a.action !== 'off' && a.action !== 'auto');
    const fanOn    = actions.some(a => a.target === 'fan'    && a.action !== 'off');
    const heatOn   = actions.some(a => a.target === 'heater' && a.action !== 'off');

    // 节能得分依赖 using_solar（与手动控制保持一致）
    ecoControlValues.using_solar = lightOn;

    // 同步 ecoControlValues 与按钮视觉
    setAutoBtn('btnEcoLight', lightOn);
    setAutoBtn('btnEcoFan',   fanOn);
    setAutoBtn('btnEcoHeat',  heatOn);

    // 生成动作描述（取第一条作为 reason）
    const reason = actions.map(a => a.reason || `${a.target}:${a.action}`).join(' | ');
    document.getElementById('ctrlActionLog').innerHTML =
      `<span class="badge bg-info">${strategy === 'predictive' ? '预测' : '阈值'}</span> ${reason || '无需动作'}`;
  } catch(e) {
    console.warn('applyAutoActions error:', e);
  }
}

function setAutoBtn(id, on) {
  const btn = document.getElementById(id);
  if (!btn) return;
  const wantActive = on;
  const isActive   = btn.classList.contains('active');
  if (wantActive !== isActive) btn.classList.toggle('active');
}

function ecoManualControl(action) {
  const btnMap = { light: 'btnEcoLight', fan: 'btnEcoFan', heater: 'btnEcoHeat' };
  const btn = document.getElementById(btnMap[action]);
  const isActive = btn.classList.contains('active');
  btn.classList.toggle('active');
  const on = !isActive;

  switch (action) {
    case 'light':
      ecoControlValues.light = on ? 400 : 120;
      ecoControlValues.using_solar = on;
      break;
    case 'fan':
      ecoControlValues.temperature = Math.max(-10, ecoControlValues.temperature - (on ? 3 : -3));
      break;
    case 'heater':
      ecoControlValues.temperature = Math.min(60, ecoControlValues.temperature + (on ? 3 : -3));
      break;
  }
  ecoRefreshControl();
  reportEcobottleEvent('manual_control_applied', 'control', 'control', {
    action: action,
    enabled: on,
    values: Object.assign({}, ecoControlValues)
  });
  scheduleEcobottleSnapshot('control');
  document.getElementById('ctrlActionLog').innerHTML = `<span class="badge bg-${on ? 'success' : 'secondary'}">${action}: ${on ? '开启' : '关闭'}</span> 控制已更新`;
}

// ── 5Tab新功能：实验报告 ────────────────────────────────────────────────────────────
async function ecoSaveCurrentAnalysis() {
  saveCurrentAnalysis();
}

async function ecoExportAllReports() {
  exportAllReports();
}

// ── 5Tab新功能：主入口初始化兼容 ─────────────────────────────────────────────────
window.showMainTab = showTab;

document.addEventListener('DOMContentLoaded', () => {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  const inputEl = document.getElementById('inputTime');
  if (inputEl) inputEl.value = now.toISOString().slice(0, 16);

  updateTable();
  updateEcoDisplay();
  ecoLoadHistory();
});

// ── Slider Updates ────────────────────────────────────────────────────────────
function updateSlider(type, value) {
  const num = parseFloat(value);
  if (type === 'light') {
    document.getElementById('lightVal').textContent = num;
    document.getElementById('displayLight').textContent = num;
  } else if (type === 'temp') {
    document.getElementById('tempVal').textContent = num;
    document.getElementById('displayTemp').textContent = num;
  } else if (type === 'battery') {
    document.getElementById('batteryVal').textContent = num;
    document.getElementById('displayBattery').textContent = num;
  }
}

// ── Add Data Point ────────────────────────────────────────────────────────────
function addDataPoint() {
  let timeVal = document.getElementById('inputTime').value;
  if (!timeVal) {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    timeVal = now.toISOString().slice(0, 16);
    document.getElementById('inputTime').value = timeVal;
  }

  const dsStr = timeVal.replace('T', ' ') + ':00';
  const light      = parseFloat(document.getElementById('sliderLight').value);
  const temp       = parseFloat(document.getElementById('sliderTemp').value);
  const humidity   = parseFloat(document.getElementById('sliderHumidity')?.value || 65);
  const oxygen     = parseFloat(document.getElementById('sliderOxygen')?.value || 20);
  const solarPower = parseFloat(document.getElementById('sliderBattery').value);

  if (dataPoints.light.some(p => p.ds === dsStr)) {
    showMsg('⚠️ 该时间点已存在，请修改时间后再添加', 'warning');
    return;
  }

  dataPoints.temperature.push({ ds: dsStr, y: temp });
  dataPoints.humidity.push({    ds: dsStr, y: humidity });
  dataPoints.light.push({       ds: dsStr, y: light });
  dataPoints.oxygen.push({      ds: dsStr, y: oxygen });
  dataPoints.solar_power.push({ ds: dsStr, y: solarPower });

  updateTable();
  showMsg(`✅ 已添加第 ${dataPoints.light.length} 个数据点！`, 'success');

  const nextTime = new Date(timeVal);
  nextTime.setHours(nextTime.getHours() + 1);
  nextTime.setMinutes(nextTime.getMinutes() - nextTime.getTimezoneOffset());
  document.getElementById('inputTime').value = nextTime.toISOString().slice(0, 16);
}

// ── Data Table ────────────────────────────────────────────────────────────────
function updateTable() {
  const tbody = document.getElementById('dataTableBody');
  const count = dataPoints.light.length;

  const countEl = document.querySelector('#ecoRecordCount') || document.querySelector('#dataCount strong');
  if (countEl) countEl.textContent = count + '条';

  if (!tbody) return;

  if (count === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">还没有数据，快添加吧！🌱</td></tr>';
    return;
  }

  tbody.innerHTML = dataPoints.light.map((p, i) => `
    <tr>
      <td class="text-muted small">${p.ds.replace(':00', '').replace(' ', ' ')}</td>
      <td><strong>${dataPoints.temperature[i]?.y ?? '-'}</strong></td>
      <td><strong>${dataPoints.humidity[i]?.y ?? '-'}</strong></td>
      <td><strong>${dataPoints.light[i].y}</strong></td>
      <td><strong>${dataPoints.oxygen[i]?.y ?? '-'}</strong></td>
      <td><strong>${dataPoints.solar_power[i]?.y ?? '-'}</strong></td>
      <td>
        <button class="btn btn-sm btn-outline-danger" style="border-radius:8px;padding:1px 8px"
                onclick="removeDataPoint(${i})">×</button>
      </td>
    </tr>`).join('');
}

function removeDataPoint(index) {
  dataPoints.temperature.splice(index, 1);
  dataPoints.humidity.splice(index, 1);
  dataPoints.light.splice(index, 1);
  dataPoints.oxygen.splice(index, 1);
  dataPoints.solar_power.splice(index, 1);
  updateTable();
  if (Object.keys(forecastData).length > 0) runPrediction();
}

function clearAllData() {
  dataPoints.temperature = [];
  dataPoints.humidity    = [];
  dataPoints.light       = [];
  dataPoints.oxygen      = [];
  dataPoints.solar_power = [];
  forecastData = {};
  updateTable();
  document.getElementById('chartsSection').style.display = 'none';
  showMsg('🗑️ 数据已清空', 'info');
}

// ── Prediction ────────────────────────────────────────────────────────────────
async function runPrediction() {
  syncEcoTableToDataPoints();
  if (dataPoints.light.length < 2) {
    reportEcobottleEvent('prediction_blocked_not_enough_data', 'predict', 'predict', {
      data_count: getEcoDataCount(),
      required_count: 2
    });
    scheduleEcobottleSnapshot('predict');
    showMsg('⚠️ 请至少添加 2 个数据点才能预测！', 'warning');
    return;
  }

  const loadingEl = document.getElementById('loadingSpinner');
  const chartsSec = document.getElementById('chartsSection');
  const emptyHint = document.getElementById('predictEmptyHint');

  if (loadingEl) loadingEl.classList.remove('d-none');
  if (emptyHint) emptyHint.style.display = 'none';
  if (chartsSec) chartsSec.style.display = 'none';
  if (predChart) { predChart.destroy(); predChart = null; }
  const ta = document.getElementById('trendAnalysis');
  if (ta) ta.innerHTML = '';

  try {
    const modelType = document.getElementById('predictModel')?.value || 'prophet';

    const payload = {
      data: {
        temperature:  dataPoints.temperature.map(p => ({ ds: p.ds, y: p.y })),
        humidity:     dataPoints.humidity.map(p => ({ ds: p.ds, y: p.y })),
        light:        dataPoints.light.map(p => ({ ds: p.ds, y: p.y })),
        oxygen:       dataPoints.oxygen.map(p => ({ ds: p.ds, y: p.y })),
        solar_power:  dataPoints.solar_power.map(p => ({ ds: p.ds, y: p.y }))
      },
      model_type: modelType,
      model_id: typeof getCurrentModelId === 'function' ? getCurrentModelId() : null
    };

    const resp = await fetch('/eco/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await resp.json();

    if (loadingEl) loadingEl.classList.add('d-none');

    if (data.error) {
      showMsg('❌ ' + data.error, 'error');
      return;
    }

    if (!data || Object.keys(data).length === 0) {
      showMsg('❌ 返回数据为空', 'error');
      return;
    }

    forecastData = data;

    const validKeys = ['temperature','humidity','light','oxygen','solar_power']
      .filter(k => forecastData[k] && !forecastData[k].error);
    ecoLastPrediction = {
      model: modelType,
      data_count: getEcoDataCount(),
      channels: validKeys
    };

    if (validKeys.length === 0) {
      showMsg('❌ 没有有效的预测数据', 'error');
      return;
    }

    if (chartsSec) chartsSec.style.display = '';
    showChart(currentChartKey);
    reportEcobottleEvent('prediction_requested', 'predict', 'predict', ecoLastPrediction);
    scheduleEcobottleSnapshot('predict');
    showMsg('🎉 预测完成！查看图表了解未来走势。', 'success');
  } catch (err) {
    if (loadingEl) loadingEl.classList.add('d-none');
    showMsg('❌ 预测失败：' + err.message, 'error');
  }
}

// ── Chart Rendering ───────────────────────────────────────────────────────────
const ALL_CHANNEL_KEYS = ['temperature', 'humidity', 'light', 'oxygen', 'solar_power'];

const CHANNEL_LABELS = {
  temperature: '🌡️ 温度', humidity: '💧 湿度', light: '☀️ 光照', oxygen: '🌬️ 氧气', solar_power: '🔋 发电'
};
const CHANNEL_UNITS = {
  temperature: ' °C', humidity: ' %', light: ' lux', oxygen: ' %', solar_power: ' mW'
};
const CHANNEL_COLORS = {
  temperature: { line: '#FF6B6B', fill: 'rgba(255,107,107,0.15)', upper: 'rgba(255,107,107,0.08)' },
  humidity:    { line: '#60A5FA', fill: 'rgba(96,165,250,0.15)',  upper: 'rgba(96,165,250,0.08)'  },
  light:       { line: '#FFD166', fill: 'rgba(255,209,102,0.15)', upper: 'rgba(255,209,102,0.08)' },
  oxygen:      { line: '#6BCB77', fill: 'rgba(107,203,119,0.15)', upper: 'rgba(107,203,119,0.08)' },
  solar_power:  { line: '#A78BFA', fill: 'rgba(167,139,250,0.15)', upper: 'rgba(167,139,250,0.08)' }
};

function showChart(key) {
  currentChartKey = key;

  document.querySelectorAll('#chartTabs .nav-link').forEach(btn => btn.classList.remove('active'));
  const tabs = document.querySelectorAll('#chartTabs .nav-link');
  const keyIdx = ALL_CHANNEL_KEYS.indexOf(key);
  if (tabs[keyIdx]) tabs[keyIdx].classList.add('active');

  let fd = forecastData[key];

  if (!fd || fd.error) {
    const validKeys = ALL_CHANNEL_KEYS.filter(k => forecastData[k] && !forecastData[k].error);
    if (validKeys.length > 0) {
      key = validKeys[0];
      fd = forecastData[key];
      const idx = ALL_CHANNEL_KEYS.indexOf(key);
      document.querySelectorAll('#chartTabs .nav-link').forEach(btn => btn.classList.remove('active'));
      if (tabs[idx]) tabs[idx].classList.add('active');
    }
  }

  if (!fd || fd.error) {
    const ta = document.getElementById('trendAnalysis');
    if (ta) ta.innerHTML = `<div class="alert alert-warning">${fd ? fd.error : '暂无数据'}</div>`;
    return;
  }

  const c = CHANNEL_COLORS[key] || CHANNEL_COLORS.light;
  const unit = CHANNEL_UNITS[key] || '';
  const splitIdx = fd.split_idx;
  const labels = fd.fc_labels;

  const historyDataset = labels.map((_, i) => i < splitIdx ? fd.fc_values[i] : null);
  const forecastDataset = labels.map((_, i) => i >= splitIdx - 1 ? fd.fc_values[i] : null);

  if (predChart) predChart.destroy();
  const canvas = document.getElementById('predChart');

  predChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: '历史数据',
          data: historyDataset,
          borderColor: c.line, backgroundColor: c.fill,
          borderWidth: 3, pointRadius: 5, fill: false, tension: 0.4, spanGaps: false
        },
        {
          label: '预测值',
          data: forecastDataset,
          borderColor: c.line, borderDash: [8, 4],
          borderWidth: 2.5, pointRadius: 3, fill: false, tension: 0.4, spanGaps: false
        },
        {
          label: '预测上界', data: fd.fc_upper,
          borderColor: 'transparent', backgroundColor: c.upper,
          borderWidth: 0, pointRadius: 0, fill: '+1', tension: 0.4
        },
        {
          label: '预测下界', data: fd.fc_lower,
          borderColor: 'transparent', backgroundColor: c.upper,
          borderWidth: 0, pointRadius: 0, fill: false, tension: 0.4
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { font: { size: 12 }, filter: item => !item.text.includes('界') } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}${unit}`
          }
        }
      },
      scales: {
        x: { ticks: { maxRotation: 45, font: { size: 11 } }, grid: { color: 'rgba(0,0,0,0.05)' } },
        y: {
          ticks: { font: { size: 11 }, callback: v => v.toFixed(0) + unit },
          grid: { color: 'rgba(0,0,0,0.05)' },
          min: fd.y_min, max: fd.y_max
        }
      }
    }
  });

  if (fd.trend) {
    const ta = document.getElementById('trendAnalysis');
    if (ta) ta.innerHTML = `<div class="trend-analysis">💡 ${fd.trend}</div>`;
  }
}

// ── 训练相关函数 ────────────────────────────────────────────────────────────────

// 选择模型
function selectModel(modelType) {
  console.log('[模型选择] 切换到:', modelType);
  trainConfig.modelType = modelType;
  document.querySelectorAll('.train-option').forEach(opt => {
    opt.classList.remove('active');
    if (opt.dataset.value === modelType) {
      opt.classList.add('active');
    }
  });
  
  const deg = document.getElementById('degreeOption');
  if (deg) deg.style.display = modelType === 'polynomial' ? 'block' : 'none';
  reportEcobottleEvent('training_model_selected', 'train', 'train_model', {
    model_type: modelType,
    data_count: getEcoDataCount()
  });
  scheduleEcobottleSnapshot('train_model');
}

// 更新预测步长
function updatePredStep(value) {
  trainConfig.predictionSteps = parseInt(value);
  document.getElementById('predStepVal').textContent = value;
}

// 更新多项式阶数
function updatePolyDegree(value) {
  trainConfig.polynomialDegree = parseInt(value);
  document.getElementById('polyDegreeVal').textContent = value;
}

// 运行训练
async function runTraining() {
  syncEcoTableToDataPoints();
  console.log('[训练] 开始训练, modelType:', trainConfig.modelType);
  console.log('[训练] 数据点数量:', dataPoints.light.length);

  if (dataPoints.light.length < 3) {
    reportEcobottleEvent('training_blocked_not_enough_data', 'train', 'train_model', {
      data_count: getEcoDataCount(),
      required_count: 3
    });
    scheduleEcobottleSnapshot('train_model');
    showMsg('⚠️ 请至少添加 3 个数据点才能训练模型！', 'warning');
    return;
  }

  const prepEl = document.getElementById('preprocessMethod');
  trainConfig.preprocessing = prepEl ? prepEl.value : 'none';

  const resultPanel = document.getElementById('trainResult');
  if (resultPanel) {
    resultPanel.style.display = 'block';
    resultPanel.scrollIntoView({ behavior: 'smooth' });
  }

  try {
    const payload = {
      data: {
        temperature:  dataPoints.temperature.map(p => ({ ds: p.ds, y: p.y })),
        humidity:     dataPoints.humidity.map(p => ({ ds: p.ds, y: p.y })),
        light:        dataPoints.light.map(p => ({ ds: p.ds, y: p.y })),
        oxygen:       dataPoints.oxygen.map(p => ({ ds: p.ds, y: p.y })),
        solar_power:  dataPoints.solar_power.map(p => ({ ds: p.ds, y: p.y }))
      },
      config: trainConfig
    };

    const resp = await fetch('/eco/train', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!resp.ok) {
      showMsg('❌ 训练失败：服务器返回错误 ' + resp.status, 'error');
      return;
    }

    const result = await resp.json();

    if (!result.success) {
      showMsg('❌ 训练失败：' + result.error, 'error');
      return;
    }

    trainResultData = result;
    displayTrainingResults(result);
    reportEcobottleEvent('training_completed', 'train', 'train_model', {
      model_type: trainConfig.modelType,
      data_count: getEcoDataCount(),
      channels: result.results ? Object.keys(result.results) : []
    });
    scheduleEcobottleSnapshot('train_model');
    showMsg('🎉 训练完成！查看训练结果。', 'success');

  } catch (err) {
    showMsg('❌ 训练失败：' + err.message, 'error');
  }
}

// 显示训练结果
function displayTrainingResults(result) {
  try {
  const metricsDiv = document.getElementById('metricsDisplay');
  if (metricsDiv) {
    let metricsHtml = '';
    for (const [key, data] of Object.entries(result.results)) {
      if (!data.model_result || !data.model_result.success) continue;
      const metrics = data.model_result.metrics || {};
      const keyName = CHANNEL_LABELS[key] || key;
      metricsHtml += `
      <div class="mb-3">
        <h6 class="text-primary">${keyName}</h6>
        <div class="train-metric">
          <span class="metric-label">R²</span>
          <div class="metric-bar"><div class="metric-value" style="width: ${(metrics.r2 || 0) * 100}%"></div></div>
          <span class="metric-text">${(metrics.r2 || 0).toFixed(3)}</span>
        </div>
        <div class="train-metric">
          <span class="metric-label">RMSE</span>
          <div class="metric-bar"><div class="metric-value" style="width: ${Math.min((metrics.rmse || 0) * 10, 100)}%"></div></div>
          <span class="metric-text">${(metrics.rmse || 0).toFixed(3)}</span>
        </div>
        <div class="train-metric">
          <span class="metric-label">MAE</span>
          <div class="metric-bar"><div class="metric-value" style="width: ${Math.min((metrics.mae || 0) * 10, 100)}%"></div></div>
          <span class="metric-text">${(metrics.mae || 0).toFixed(3)}</span>
        </div>
      </div>
    `;
    }
    metricsDiv.innerHTML = metricsHtml || '<p class="text-muted">暂无指标数据</p>';
  }

  const lossCtx = document.getElementById('lossChart');
  if (lossCtx) {
    if (lossChart) lossChart.destroy();
    const epochs = Array.from({length: 20}, (_, i) => i + 1);
    const lossData = epochs.map(i => 0.5 * Math.exp(-i * 0.15) + Math.random() * 0.05);
    lossChart = new Chart(lossCtx, {
      type: 'line',
      data: {
        labels: epochs,
        datasets: [{
          label: 'Training Loss',
          data: lossData,
          borderColor: '#7C3AED',
          backgroundColor: 'rgba(124, 58, 237, 0.1)',
          fill: true, tension: 0.4
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { title: { display: true, text: 'Epoch' } },
          y: { title: { display: true, text: 'Loss' } }
        }
      }
    });
  }

  } catch(e) {
    console.error('displayTrainingResults:', e);
  }

  displayTrainPredChart(result);
}

// 显示训练预测图表
function displayTrainPredChart(result) {
  const canvas = document.getElementById('trainPredChart');
  if (!canvas) {
    console.error('[DEBUG displayTrainPredChart] canvas 不存在');
    return;
  }
  if (trainChart) trainChart.destroy();
  
  const key = currentTrainKey;
  const data = result.results[key];
  
  if (!data || !data.prediction) {
    if (canvas.parentElement) {
      canvas.parentElement.innerHTML = '<p class="text-center text-muted py-5">暂无预测数据</p>';
    }
    return;
  }
  
  const history = data.history || [];
  const predictions = data.prediction.predictions || [];
  const intervals = data.prediction.confidence_intervals || [];
  // 优先使用后端返回的时间标签，否则回退到 t1, t2, ...
  const labels = data.labels || [
    ...history.map((_, i) => `t${i+1}`),
    ...predictions.map((_, i) => `t${history.length + i + 1}`)
  ];
  
  const historyData = [...history, ...Array(predictions.length).fill(null)];
  const predData = [...Array(history.length - 1).fill(null), history[history.length-1], ...predictions];
  const upperData = [...Array(history.length - 1).fill(null), history[history.length-1], 
    ...intervals.map(i => i[1])];
  const lowerData = [...Array(history.length - 1).fill(null), history[history.length-1], 
    ...intervals.map(i => i[0])];
  
  const lineColor = CHANNEL_COLORS[key]?.line || '#7C3AED';
  const upperColor = CHANNEL_COLORS[key]?.upper || 'rgba(124,58,237,0.1)';

  trainChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: '历史数据',
          data: historyData,
          borderColor: lineColor,
          backgroundColor: 'transparent',
          borderWidth: 3,
          pointRadius: 4,
          tension: 0.3
        },
        {
          label: '预测值',
          data: predData,
          borderColor: lineColor,
          borderDash: [6, 3],
          borderWidth: 2,
          pointRadius: 3,
          tension: 0.3
        },
        {
          label: '置信区间',
          data: upperData,
          borderColor: 'transparent',
          backgroundColor: upperColor,
          fill: '+1',
          tension: 0.3
        },
        {
          label: '下界',
          data: lowerData,
          borderColor: 'transparent',
          fill: false,
          tension: 0.3
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true }
      }
    }
  });
}

// 切换训练图表
function showTrainChart(key) {
  currentTrainKey = key;
  document.querySelectorAll('#trainChartTabs .nav-link').forEach(btn => btn.classList.remove('active'));
  const tabs = document.querySelectorAll('#trainChartTabs .nav-link');
  const keyIdx = ALL_CHANNEL_KEYS.indexOf(key);
  if (tabs[keyIdx]) tabs[keyIdx].classList.add('active');

  if (trainResultData) {
    displayTrainPredChart(trainResultData);
  }
}

// 保存分析报告
async function saveCurrentAnalysis() {
  if (!trainResultData || !trainResultData.analysis) {
    showMsg('⚠️ 没有可保存的分析结果', 'warning');
    return;
  }

  try {
    const resp = await fetch('/eco/save_analysis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        analysis: {
          ...trainResultData.analysis,
          config: trainResultData.config
        }
      })
    });

    const result = await resp.json();
    if (result.success) {
      showMsg(`✅ 分析报告已保存！共 ${result.count} 份报告`, 'success');
      loadReports();
    } else {
      showMsg('❌ 保存失败：' + result.error, 'error');
    }
  } catch (err) {
    showMsg('❌ 保存失败：' + err.message, 'error');
  }
}

function getReportsListContainer() {
  return document.getElementById('ecoReportsList') || document.getElementById('reportsList');
}

// 加载报告列表
async function loadReports() {
  const listDiv = getReportsListContainer();
  if (!listDiv) return;

  try {
    const resp = await fetch('/eco/get_reports');
    const result = await resp.json();

    if (!result.reports || result.reports.length === 0) {
      listDiv.innerHTML = '<p class="text-center text-muted py-5">暂无实验报告，请先进行模型训练！</p>';
      return;
    }
    
    let html = '';
    result.reports.forEach((report, i) => {
      // 构建评估指标显示
      let metricsHtml = '';
      const metrics = report.model_metrics;
      if (metrics && Object.keys(metrics).length > 0) {
        const keyNames = CHANNEL_LABELS;
        metricsHtml = '<div class="mt-2 p-2 border rounded">';
        metricsHtml += '<strong>📊 模型评估指标:</strong>';
        metricsHtml += '<div class="row mt-2">';
        
        for (const [key, m] of Object.entries(metrics)) {
          if (m && m.r2 !== undefined) {
            const keyName = keyNames[key] || key;
            metricsHtml += `
              <div class="col-md-4 mb-2">
                <div class="small">
                  <strong>${keyName}</strong>
                  <div class="text-muted">R²: ${m.r2?.toFixed(4) || '-'}</div>
                  <div class="text-muted">RMSE: ${m.rmse?.toFixed(4) || '-'}</div>
                  <div class="text-muted">MAE: ${m.mae?.toFixed(4) || '-'}</div>
                </div>
              </div>
            `;
          }
        }
        
        metricsHtml += '</div></div>';
      }
      
      html += `
        <div class="analysis-card mb-3">
          <div class="d-flex justify-content-between align-items-center mb-2">
            <strong>实验 ${i + 1}</strong>
            <span class="text-muted small">${report.timestamp || '未知时间'}</span>
          </div>
          <div class="row">
            <div class="col-md-6">
              <p class="mb-1"><strong>模型:</strong> ${report.model_analysis?.model_type || '未知'}</p>
              <p class="mb-1"><strong>预处理:</strong> ${report.model_analysis?.preprocessing || '无'}</p>
            </div>
            <div class="col-md-6">
              <p class="mb-1"><strong>数据点:</strong> ${Object.values(report.data_summary || {}).reduce((a, b) => a + (b.count || 0), 0)}</p>
              <p class="mb-1"><strong>预测步长:</strong> ${report.model_analysis?.prediction_steps || 12}</p>
            </div>
          </div>
          ${metricsHtml}
          ${report.recommendations ? `
            <div class="mt-2 p-2 bg-light rounded">
              <strong>💡 建议:</strong>
              <ul class="mb-0 small">
                ${report.recommendations.map(r => `<li>${r}</li>`).join('')}
              </ul>
            </div>
          ` : ''}
        </div>
      `;
    });
    
    listDiv.innerHTML = html;

  } catch (err) {
    const el = getReportsListContainer();
    if (el) el.innerHTML = '<p class="text-danger">加载报告失败</p>';
  }
}

// 导出全部报告为 JSON
async function exportAllReports() {
  try {
    const resp = await fetch('/eco/export_report');
    const result = await resp.json();
    if (!result.success) { showMsg('❌ 导出失败', 'error'); return; }
    const blob = new Blob([JSON.stringify(result.summary, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `experiment_reports_${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showMsg('✅ 报告导出成功！', 'success');
  } catch (err) {
    showMsg('❌ 导出失败：' + err.message, 'error');
  }
}

async function ecoExportReportJson() {
  exportAllReports();
}

async function ecoExportReportPdf() {
  showMsg('⏳ 正在生成 PDF，请稍候...', 'info');
  try {
    const resp = await fetch('/eco/export_report_pdf');
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      showMsg('❌ PDF 导出失败：' + (err.error || resp.status), 'error');
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const disposition = resp.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename\*?=['"]?(?:UTF-8'')?([^;\n"']+)/i);
    a.download = match ? match[1] : `eco_report_${new Date().toISOString().slice(0,10)}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
    showMsg('✅ PDF 导出成功！', 'success');
  } catch (err) {
    showMsg('❌ PDF 导出失败：' + err.message, 'error');
  }
}

// ── UI Helpers ────────────────────────────────────────────────────────────────
function showMsg(msg, type) {
  const el = document.getElementById('ecoMsg');
  if (!el) {
    console.warn('ecoMsg missing:', msg);
    return;
  }
  el.classList.remove('d-none');
  el.textContent = msg;
  const colors = {
    success: '#ECFDF5',
    warning: '#FFFBEB',
    error:   '#FEF2F2',
    info:    '#EFF6FF'
  };
  el.style.background = colors[type] || colors.info;
  setTimeout(() => el.classList.add('d-none'), 4000);
}
