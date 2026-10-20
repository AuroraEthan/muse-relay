/* Exact-message onboarding receipt. No transmission occurs until send() is called. */
(function (root) {
  'use strict';
  class RelayTest {
    constructor(storage, unique = () => crypto.randomUUID()) {
      this.storage = storage;
      this.unique = unique;
      this.records = new Map();
      this.busy = new Set();
    }
    read(id) {
      if (!this.records.has(id)) {
        let value;
        try { value = JSON.parse(this.storage.getItem('muse-test:' + id)); } catch (_) {}
        const valid = value && typeof value.messageId === 'string';
        const pending = value?.pending;
        this.records.set(id, {
          messageId: valid ? value.messageId : null,
          status: valid ? value.status : null,
          pending: pending && typeof pending.key === 'string' && typeof pending.text === 'string' ? pending : null
        });
      }
      return {...this.records.get(id), busy: this.busy.has(id)};
    }
    save(id, value) {
      this.records.set(id, value);
      try { this.storage.setItem('muse-test:' + id, JSON.stringify(value)); } catch (_) {}
    }
    async send(id, request) {
      if (this.busy.has(id)) return;
      const value = this.read(id);
      if (!value.pending) {
        value.pending = {key: this.unique(), text: 'Muse Relay 연결 테스트 · ' + new Date().toISOString()};
        value.messageId = null;
        value.status = null;
      }
      this.busy.add(id);
      this.save(id, value);
      try {
        const result = await request(value.pending);
        this.save(id, {pending: null, messageId: result.id, status: 'pending'});
        return result;
      } catch (error) {
        if (!error.uncertain && error.status !== 429) {
          value.pending = null;
          this.save(id, value);
        }
        throw error;
      } finally {
        this.busy.delete(id);
      }
    }
    observe(id, message) {
      const value = this.read(id);
      if (value.messageId === message.id) {
        value.status = message.status;
        this.save(id, value);
      }
    }
  }
  if (typeof module !== 'undefined') module.exports = {RelayTest};
  else root.RelayTest = RelayTest;
})(typeof window === 'undefined' ? globalThis : window);
