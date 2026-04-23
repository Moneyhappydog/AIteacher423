/* File Tree Component — 新增文件/文件夹创建功能 */

const FILE_TREE_DATA = {
  'face_cnn': {
    open: true,
    children: [
      { name: 'train.py', icon: '🐍', type: 'file' },
      { name: 'model.py', icon: '🔧', type: 'file' },
      { name: 'README.md', icon: '📄', type: 'file' },
    ]
  },
  'eco_lstm': {
    open: false,
    children: [
      { name: 'train.py', icon: '🐍', type: 'file' },
      { name: 'README.md', icon: '📄', type: 'file' },
    ]
  },
  'eco_arima': {
    open: false,
    children: [
      { name: 'train.py', icon: '🐍', type: 'file' },
      { name: 'README.md', icon: '📄', type: 'file' },
    ]
  }
};

// 新增：用户创建的文件夹结构
const USER_CREATED_FILES = {
  'data': {
    open: true,
    children: [
      { name: 'face', icon: '📁', type: 'folder' },
      { name: 'labels.csv', icon: '📄', type: 'file' },
    ]
  },
  'models': {
    open: false,
    children: []
  },
  'utils': {
    open: false,
    children: []
  }
};

// 跟踪用户创建的文件夹
let userFolders = ['data', 'models', 'utils'];
let userFiles = [
  { folder: 'data', name: 'labels.csv' }
];

function renderFileTree() {
  const container = document.getElementById('fileTree');
  if (!container) return;

  const tmpl = typeof currentTemplate !== 'undefined' ? currentTemplate : 'face_cnn';
  let html = '';

  // 新增按钮区域
  html += `
  <div class="ft-actions" style="padding:4px 8px;display:flex;gap:4px;margin-bottom:8px">
    <button class="ft-action-btn" onclick="createNewFile()" title="新建文件">
      <span>📄</span> 新建文件
    </button>
    <button class="ft-action-btn" onclick="createNewFolder()" title="新建文件夹">
      <span>📁</span> 新建文件夹
    </button>
  </div>`;

  // 用户创建的文件夹（小组工作目录）
  if (userFolders.length > 0) {
    html += `<div class="ft-section-label" style="font-size:0.7rem;color:#808080;padding:2px 8px 4px">小组工作目录</div>`;
    userFolders.forEach(folderName => {
      const folderData = USER_CREATED_FILES[folderName] || { open: false, children: [] };
      const isOpen = folderData.open;
      html += renderFolderNode(folderName, folderData, isOpen, true);
    });
  }

  // 模板文件夹
  html += `<div class="ft-section-label" style="font-size:0.7rem;color:#808080;padding:8px 8px 4px;border-top:1px solid #3c3c3c;margin-top:8px">代码模板</div>`;
  for (const [folderName, folderData] of Object.entries(FILE_TREE_DATA)) {
    const isOpen = folderData.open || folderName === tmpl;
    const folderIcon = folderName.includes('eco') ? '🌿' : '😀';
    const folderLabel = {
      'face_cnn': '表情CNN',
      'eco_lstm': '生态LSTM',
      'eco_arima': '生态ARIMA'
    }[folderName] || folderName;

    html += renderFolderNode(folderName, folderData, isOpen, false, folderIcon, folderLabel);
  }

  // 打开的文件
  const openFilesList = typeof openTabs !== 'undefined' ? openTabs : [];
  if (openFilesList.length > 0) {
    html += `<div style="margin-top:8px;padding-top:8px;border-top:1px solid #3c3c3c">
      <div style="font-size:0.72rem;color:#808080;padding:0 8px 4px">打开的文件</div>`;
    openFilesList.forEach(tab => {
      const icon = tab.name.endsWith('.py') ? '🐍' : '📄';
      html += `
        <div class="ft-item ${tab.path === activeTabPath ? 'active' : ''}"
             onclick="switchTab('${tab.path}')">
          <span class="ft-icon">${icon}</span>
          <span class="ft-name">${tab.name}</span>
        </div>`;
    });
    html += '</div>';
  }

  container.innerHTML = html;
}

function renderFolderNode(folderName, folderData, isOpen, isUserFolder, folderIcon = '📁', folderLabel = folderName) {
  const childrenHtml = folderData.children.map(f => {
    const fName = f.name || f;
    const fType = f.type || (fName.includes('.') ? 'file' : 'folder');
    const fIcon = f.icon || (fType === 'folder' ? '📁' : '🐍');
    const isActive = fName === activeTabPath;
    return `
      <div class="ft-item ${isActive ? 'active' : ''}"
           data-file="${fName}"
           data-folder="${folderName}"
           onclick="${fType === 'folder' ? `toggleFolder('${fName}')` : `openFileFromTree('${fName}', '${isUserFolder ? 'user' : folderName}')`}">
        <span class="ft-icon">${fIcon}</span>
        <span class="ft-name">${fName}</span>
        ${fType === 'file' ? `<span class="ft-delete" onclick="event.stopPropagation();deleteFile('${fName}','${folderName}')" title="删除文件">×</span>` : ''}
      </div>`;
  }).join('');

  return `
    <div class="ft-folder">
      <div class="ft-folder-header" onclick="toggleFolder('${folderName}', ${isUserFolder})">
        <span class="ft-chevron ${isOpen ? 'open' : ''}" id="chevron-${isUserFolder ? 'user-' : ''}${folderName}">▶</span>
        <span>${folderIcon}</span>
        <span style="flex:1">${folderLabel}</span>
        ${isUserFolder ? `<span class="ft-delete" onclick="event.stopPropagation();deleteFolder('${folderName}')" title="删除文件夹">×</span>` : ''}
      </div>
      <div class="ft-fildren ${isOpen ? 'open' : ''}" id="folder-${isUserFolder ? 'user-' : ''}${folderName}">
        ${childrenHtml}
      </div>
    </div>`;
}

function toggleFolder(folderName, isUserFolder = false) {
  const prefix = isUserFolder ? 'user-' : '';
  const children = document.getElementById('folder-' + prefix + folderName);
  const chevron = document.getElementById('chevron-' + prefix + folderName);
  if (!children) return;

  const isOpen = children.classList.contains('open');
  children.classList.toggle('open');
  chevron.classList.toggle('open', !isOpen);
}

function openFileFromTree(filename, folderName) {
  let code = '';

  // 检查用户创建的文件夹
  if (folderName === 'user') {
    // 从USER_CREATED_FILES中查找
    for (const [fName, fData] of Object.entries(USER_CREATED_FILES)) {
      const found = fData.children.find(c => (c.name || c) === filename);
      if (found) {
        code = typeof found.code !== 'undefined' ? found.code : `# ${filename}\n# 用户创建的文件\n`;
        break;
      }
    }
  } else if (TEMPLATE_FILES[folderName]) {
    code = TEMPLATE_FILES[folderName][filename] || '';
  }

  const lang = filename.endsWith('.py') ? 'python' : filename.endsWith('.md') ? 'markdown' : 'python';

  const existing = openTabs.find(t => t.path === filename);
  if (existing) {
    switchTab(filename);
    return;
  }

  openTabs.push({ name: filename, path: filename, code, lang });
  switchTab(filename);
  renderFileTree();
}

// 新建文件
function createNewFile() {
  const name = prompt('请输入文件名（如：my_script.py）:', 'new_file.py');
  if (!name || !name.trim()) return;

  let fileName = name.trim();
  if (!fileName.includes('.')) {
    fileName += '.py'; // 默认添加 .py 扩展名
  }

  // 检查是否已存在
  if (isFileExists(fileName)) {
    appendTerminal('sys', '⚠️ 文件已存在: ' + fileName);
    return;
  }

  // 创建默认代码内容
  const defaultCode = `# ${fileName}\n# 创建时间: ${new Date().toLocaleString()}\n\n`;

  // 添加到默认文件夹（utils）
  const targetFolder = 'utils';
  if (!USER_CREATED_FILES[targetFolder]) {
    USER_CREATED_FILES[targetFolder] = { open: true, children: [] };
  }
  if (!userFolders.includes(targetFolder)) {
    userFolders.push(targetFolder);
  }

  USER_CREATED_FILES[targetFolder].children.push({
    name: fileName,
    icon: fileName.endsWith('.py') ? '🐍' : '📄',
    type: 'file',
    code: defaultCode
  });

  userFiles.push({ folder: targetFolder, name: fileName });
  openTabs.push({ name: fileName, path: fileName, code: defaultCode, lang: fileName.endsWith('.py') ? 'python' : 'markdown' });
  switchTab(fileName);
  renderFileTree();
  appendTerminal('sys', '✅ 已创建文件: ' + fileName);
}

// 新建文件夹
function createNewFolder() {
  const name = prompt('请输入文件夹名称:', 'new_folder');
  if (!name || !name.trim()) return;

  let folderName = name.trim().replace(/[^a-zA-Z0-9_\u4e00-\u9fa5-]/g, '_');

  if (userFolders.includes(folderName)) {
    appendTerminal('sys', '⚠️ 文件夹已存在: ' + folderName);
    return;
  }

  userFolders.push(folderName);
  USER_CREATED_FILES[folderName] = { open: true, children: [] };
  renderFileTree();
  appendTerminal('sys', '✅ 已创建文件夹: ' + folderName);
}

// 检查文件是否存在
function isFileExists(fileName) {
  for (const [_, fData] of Object.entries(USER_CREATED_FILES)) {
    if (fData.children.some(c => (c.name || c) === fileName)) {
      return true;
    }
  }
  return false;
}

// 删除文件
function deleteFile(fileName, folderName) {
  if (!confirm(`确定要删除文件 "${fileName}" 吗？`)) return;

  // 从对应文件夹中删除
  if (USER_CREATED_FILES[folderName]) {
    const idx = USER_CREATED_FILES[folderName].children.findIndex(c => (c.name || c) === fileName);
    if (idx !== -1) {
      USER_CREATED_FILES[folderName].children.splice(idx, 1);
    }
  }

  // 如果文件在打开的标签中，关闭它
  const tabIdx = openTabs.findIndex(t => t.path === fileName);
  if (tabIdx !== -1) {
    closeTab(fileName);
  }

  // 从userFiles中删除
  const ufIdx = userFiles.findIndex(f => f.name === fileName);
  if (ufIdx !== -1) {
    userFiles.splice(ufIdx, 1);
  }

  renderFileTree();
  appendTerminal('sys', '🗑️ 已删除文件: ' + fileName);
}

// 删除文件夹
function deleteFolder(folderName) {
  if (!confirm(`确定要删除文件夹 "${folderName}" 及其所有内容吗？`)) return;

  // 删除文件夹中的所有文件
  if (USER_CREATED_FILES[folderName]) {
    USER_CREATED_FILES[folderName].children.forEach(f => {
      const tabIdx = openTabs.findIndex(t => t.path === (f.name || f));
      if (tabIdx !== -1) {
        closeTab(f.name || f);
      }
    });
  }

  delete USER_CREATED_FILES[folderName];
  const idx = userFolders.indexOf(folderName);
  if (idx !== -1) {
    userFolders.splice(idx, 1);
  }

  // 清理userFiles中属于该文件夹的文件
  userFiles = userFiles.filter(f => f.folder !== folderName);

  renderFileTree();
  appendTerminal('sys', '🗑️ 已删除文件夹: ' + folderName);
}
