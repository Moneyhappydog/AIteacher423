(function (window) {
  'use strict';

  const DEFAULT_EVENT_ENDPOINT = '/ai/context/event';
  const DEFAULT_SNAPSHOT_ENDPOINT = '/ai/context/snapshot';
  const SESSION_PREFIX = 'ai_tutor_session';

  function nowIso() {
    return new Date().toISOString();
  }

  function safeJsonClone(value) {
    if (value == null) return value;
    try {
      return JSON.parse(JSON.stringify(value));
    } catch (err) {
      return {};
    }
  }

  function randomId() {
    const randomPart = Math.random().toString(36).slice(2, 10);
    return `${Date.now().toString(36)}_${randomPart}`;
  }

  function storageKey(page, course) {
    return `${SESSION_PREFIX}:${page || 'unknown'}:${course || 'unknown'}`;
  }

  function createSessionId(page, course) {
    const prefix = (page || course || 'ai').replace(/[^a-zA-Z0-9_]/g, '_');
    return `${prefix}_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}_${randomId()}`;
  }

  function getStoredSessionId(page, course) {
    const key = storageKey(page, course);
    try {
      const existing = window.sessionStorage.getItem(key);
      if (existing) return existing;
      const created = createSessionId(page, course);
      window.sessionStorage.setItem(key, created);
      return created;
    } catch (err) {
      return createSessionId(page, course);
    }
  }

  function mergeConfig(current, next) {
    return Object.assign({}, current, next || {});
  }

  function getGlobalAskMode() {
    if (typeof window.getAiAskMode === 'function') {
      try {
        return window.getAiAskMode();
      } catch (err) {
        return 'simple';
      }
    }
    return window.__aiAskMode === 'context' ? 'context' : 'simple';
  }

  function Tracker() {
    this.config = {
      page: null,
      course: null,
      stepCode: null,
      groupId: null,
      memberId: null,
      eventEndpoint: DEFAULT_EVENT_ENDPOINT,
      snapshotEndpoint: DEFAULT_SNAPSHOT_ENDPOINT,
      enabled: true
    };
    this.sessionId = null;
    this.snapshotProvider = null;
    this.lastSnapshot = {};
    this.pendingSnapshotTimer = null;
  }

  Tracker.prototype.init = function init(config) {
    this.config = mergeConfig(this.config, config);
    this.sessionId = this.config.sessionId || getStoredSessionId(this.config.page, this.config.course);
    if (typeof this.config.snapshotProvider === 'function') {
      this.snapshotProvider = this.config.snapshotProvider;
    }
    return this;
  };

  Tracker.prototype.configure = function configure(config) {
    this.config = mergeConfig(this.config, config);
    if (config && config.sessionId) {
      this.sessionId = config.sessionId;
    }
    if (config && typeof config.snapshotProvider === 'function') {
      this.snapshotProvider = config.snapshotProvider;
    }
    return this;
  };

  Tracker.prototype.getSessionId = function getSessionId() {
    if (!this.sessionId) {
      this.sessionId = getStoredSessionId(this.config.page, this.config.course);
    }
    return this.sessionId;
  };

  Tracker.prototype.setStep = function setStep(stepCode) {
    this.config.stepCode = stepCode || this.config.stepCode;
    return this;
  };

  Tracker.prototype.setSnapshotProvider = function setSnapshotProvider(provider) {
    if (typeof provider === 'function') {
      this.snapshotProvider = provider;
    }
    return this;
  };

  Tracker.prototype.getSnapshot = function getSnapshot(extra) {
    let snapshot = {};
    if (typeof this.snapshotProvider === 'function') {
      try {
        snapshot = this.snapshotProvider() || {};
      } catch (err) {
        snapshot = {};
      }
    }
    this.lastSnapshot = Object.assign({}, safeJsonClone(snapshot), safeJsonClone(extra) || {});
    return this.lastSnapshot;
  };

  Tracker.prototype.buildBasePayload = function buildBasePayload(extra) {
    const data = extra || {};
    return Object.assign({
      session_id: this.getSessionId(),
      group_id: data.group_id || this.config.groupId,
      member_id: data.member_id || this.config.memberId,
      page: data.page || this.config.page,
      course: data.course || this.config.course,
      step_code: data.step_code || data.stepCode || this.config.stepCode
    }, data);
  };

  Tracker.prototype.buildAskContext = function buildAskContext(extraSnapshot) {
    return this.buildBasePayload({
      snapshot: this.getSnapshot(extraSnapshot)
    });
  };

  Tracker.prototype.getAskMode = function getAskMode() {
    return getGlobalAskMode();
  };

  Tracker.prototype.isContextModeEnabled = function isContextModeEnabled() {
    return this.getAskMode() === 'context';
  };

  Tracker.prototype.postJson = async function postJson(url, payload) {
    if (!this.config.enabled) return { skipped: true };
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(payload)
      });
      return await response.json().catch(() => ({ success: response.ok }));
    } catch (err) {
      return { success: false, error: err.message };
    }
  };

  Tracker.prototype.reportEvent = function reportEvent(eventName, options) {
    const opts = options || {};
    if (!eventName) return Promise.resolve({ success: false, error: 'eventName is required' });
    if (!this.isContextModeEnabled()) {
      return Promise.resolve({
        skipped: true,
        reason: 'ask_mode_simple',
        ask_mode: this.getAskMode()
      });
    }

    const payload = this.buildBasePayload({
      step_code: opts.stepCode || opts.step_code || this.config.stepCode,
      event_type: opts.eventType || opts.event_type || 'ui',
      event_name: eventName,
      payload: safeJsonClone(opts.payload || {}),
      summary_text: opts.summaryText || opts.summary_text,
      dedupe_key: opts.dedupeKey || opts.dedupe_key,
      event_time: opts.eventTime || opts.event_time || nowIso()
    });
    return this.postJson(this.config.eventEndpoint, payload);
  };

  Tracker.prototype.reportSnapshot = function reportSnapshot(options) {
    const opts = options || {};
    if (!this.isContextModeEnabled()) {
      return Promise.resolve({
        skipped: true,
        reason: 'ask_mode_simple',
        ask_mode: this.getAskMode()
      });
    }
    const payload = this.buildBasePayload({
      step_code: opts.stepCode || opts.step_code || this.config.stepCode,
      snapshot: this.getSnapshot(opts.extraSnapshot),
      diagnosis: opts.diagnosis
    });
    return this.postJson(this.config.snapshotEndpoint, payload);
  };

  Tracker.prototype.scheduleSnapshot = function scheduleSnapshot(delayMs, options) {
    const delay = typeof delayMs === 'number' ? delayMs : 500;
    clearTimeout(this.pendingSnapshotTimer);
    this.pendingSnapshotTimer = setTimeout(() => {
      this.reportSnapshot(options || {});
    }, delay);
  };

  Tracker.prototype.wrapAskPayload = function wrapAskPayload(question, payload) {
    return Object.assign({}, payload || {}, {
      question: question,
      context: Object.assign({}, (payload && payload.context) || {}, this.buildAskContext())
    });
  };

  window.AiContextTracker = new Tracker();
})(window);
