(function (window, document) {
  'use strict';

  const HIGHLIGHT_CLASS = 'ai-action-highlight';

  function ensureHighlightStyle() {
    if (document.getElementById('ai-course-bridge-style')) return;
    const style = document.createElement('style');
    style.id = 'ai-course-bridge-style';
    style.textContent = `
      .${HIGHLIGHT_CLASS} {
        position: relative;
        outline: 3px solid rgba(124, 58, 237, 0.55) !important;
        box-shadow: 0 0 0 6px rgba(124, 58, 237, 0.16) !important;
        transition: box-shadow 160ms ease, outline-color 160ms ease;
      }
    `;
    document.head.appendChild(style);
  }

  function callIfFunction(fn, args) {
    if (typeof fn !== 'function') return undefined;
    return fn.apply(null, args || []);
  }

  function Bridge() {
    this.page = null;
    this.course = null;
    this.actions = {};
    this.snapshotProvider = null;
  }

  Bridge.prototype.init = function init(options) {
    const opts = options || {};
    this.page = opts.page || this.page;
    this.course = opts.course || this.course;
    this.actions = Object.assign({}, this.actions, opts.actions || {});
    if (typeof opts.snapshotProvider === 'function') {
      this.snapshotProvider = opts.snapshotProvider;
    }

    if (window.AiContextTracker) {
      window.AiContextTracker.init({
        page: this.page,
        course: this.course,
        groupId: opts.groupId,
        memberId: opts.memberId,
        stepCode: opts.stepCode,
        snapshotProvider: this.snapshotProvider
      });
    }
    return this;
  };

  Bridge.prototype.registerAction = function registerAction(name, fn) {
    if (name && typeof fn === 'function') {
      this.actions[name] = fn;
    }
    return this;
  };

  Bridge.prototype.registerSnapshotProvider = function registerSnapshotProvider(provider) {
    if (typeof provider === 'function') {
      this.snapshotProvider = provider;
      if (window.AiContextTracker) {
        window.AiContextTracker.setSnapshotProvider(provider);
      }
    }
    return this;
  };

  Bridge.prototype.track = function track(eventName, options) {
    if (!window.AiContextTracker) return Promise.resolve({ skipped: true });
    return window.AiContextTracker.reportEvent(eventName, options || {});
  };

  Bridge.prototype.snapshot = function snapshot(options) {
    if (!window.AiContextTracker) return Promise.resolve({ skipped: true });
    return window.AiContextTracker.reportSnapshot(options || {});
  };

  Bridge.prototype.getAskContext = function getAskContext(extraSnapshot) {
    if (!window.AiContextTracker) return {};
    return window.AiContextTracker.buildAskContext(extraSnapshot);
  };

  Bridge.prototype.highlight = function highlight(selector, durationMs) {
    const el = typeof selector === 'string' ? document.querySelector(selector) : selector;
    if (!el) return false;
    ensureHighlightStyle();
    el.classList.add(HIGHLIGHT_CLASS);
    const duration = typeof durationMs === 'number' ? durationMs : 3500;
    window.setTimeout(() => el.classList.remove(HIGHLIGHT_CLASS), duration);
    return true;
  };

  Bridge.prototype.switchTab = function switchTab(tabName) {
    if (!tabName) return false;
    if (typeof this.actions.switchTab === 'function') {
      this.actions.switchTab(tabName);
      return true;
    }
    if (typeof window.showTab === 'function') {
      window.showTab(tabName);
      return true;
    }
    return false;
  };

  Bridge.prototype.applyHint = function applyHint(hint) {
    const action = hint || {};
    if (action.type === 'highlight' && action.selector) {
      return this.highlight(action.selector, action.duration_ms);
    }
    if (action.type === 'switch_tab' && action.tab) {
      return this.switchTab(action.tab);
    }
    if (action.name && this.actions[action.name]) {
      callIfFunction(this.actions[action.name], action.args || []);
      return true;
    }
    return false;
  };

  Bridge.prototype.attachAskContext = function attachAskContext(payload) {
    const data = Object.assign({}, payload || {});
    data.context = Object.assign({}, data.context || {}, this.getAskContext());
    return data;
  };

  window.AiCourseBridge = new Bridge();
})(window, document);
