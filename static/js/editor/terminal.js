/* Terminal Output Component */

function appendTerminal(type, text) {
  const output = document.getElementById('terminalOutput');
  if (!output) return;

  const line = document.createElement('div');
  line.className = 'term-line term-' + type;

  // Image path: show placeholder (actual image loading requires server support)
  if (type === 'img') {
    line.innerHTML = `<div class="term-img-placeholder">📊 图表已生成（${text}）</div>`;
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
    return;
  }

  // Escape HTML
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Colorize ANSI-like output
  const colorized = ansiToHtml(escaped);
  line.innerHTML = colorized;

  output.appendChild(line);
  output.scrollTop = output.scrollHeight;
}

function clearTerminal() {
  const output = document.getElementById('terminalOutput');
  if (output) output.innerHTML = '';
  appendTerminal('sys', '🗑️ 终端已清空');
}

function ansiToHtml(text) {
  // Simple ANSI color code stripper + basic highlighting
  // Strip ANSI codes
  const stripped = text.replace(/\x1b\[[0-9;]*m/g, '');

  // Highlight Python keywords
  const keywords = ['import', 'from', 'def', 'class', 'return', 'if', 'else', 'elif',
    'for', 'while', 'try', 'except', 'finally', 'with', 'as', 'lambda', 'yield',
    'print', 'True', 'False', 'None', 'and', 'or', 'not', 'in', 'is'];

  let result = stripped;

  // Highlight strings
  result = result.replace(/(["'])((?:\\.|(?!\1)[^\\])*)\1/g,
    '<span style="color:#ce9178">$&</span>');

  // Highlight numbers
  result = result.replace(/\b(\d+\.?\d*)\b/g,
    '<span style="color:#b5cea8">$1</span>');

  // Highlight keywords (but not inside strings)
  keywords.forEach(kw => {
    const re = new RegExp(`\\b(${kw})\\b`, 'g');
    result = result.replace(re, '<span style="color:#569cd6;font-weight:600">$1</span>');
  });

  // Highlight comments
  result = result.replace(/(#.*)$/gm, '<span style="color:#6a9955;font-style:italic">$1</span>');

  return result;
}

// Auto-scroll terminal on new output
const _originalAppend = window.appendTerminal;
window.appendTerminal = function(type, text) {
  // Call original (this would be redundant if we just use the function above)
  const output = document.getElementById('terminalOutput');
  if (!output) return;

  const line = document.createElement('div');
  line.className = 'term-line term-' + type;

  if (type === 'img') {
    line.innerHTML = `<div class="term-img-placeholder">📊 图表已生成</div>`;
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
    return;
  }

  const colorMap = {
    stdout: '#d4d4d4',
    stderr: '#f48771',
    sys: '#569cd6',
    result: '#c5c5c5',
    running: '#4ec9b0',
    img: '#4ec9b0'
  };

  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  const color = colorMap[type] || '#d4d4d4';
  line.innerHTML = `<span style="color:${color}">${escaped}</span>`;
  output.appendChild(line);
  output.scrollTop = output.scrollHeight;
};
