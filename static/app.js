'use strict';
(() => {
  const $ = id => document.getElementById(id);
  if (!$('relay-app')) return;
  const state = {token: '', connected: false, publicSend: false, retryKey: null, retryText: null, before: null, next: null, loading: false, sending: false, generation: 0};
  const labels = {pending: '대기 중', leased: 'VM 가져감', acked: '전달 완료'};
  function notice(text, error = false) {
    $('notice').textContent = text;
    $('notice').classList.remove('hidden');
    $('notice').classList.toggle('error', error);
  }
  function badge(text, connected = false) {
    const dot = document.createElement('span'); dot.className = 'dot' + (connected ? '' : ' neutral');
    $('connection-badge').replaceChildren(dot, document.createTextNode(text));
  }
  async function api(path, options = {}) {
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 15000);
    try {
      const {contentType, requestKey, ...fetchOptions} = options;
      const response = await fetch(path, {...fetchOptions, signal: abort.signal, cache: 'no-store', credentials: 'same-origin',
        headers: {...(state.token ? {'Authorization': 'Bearer ' + state.token} : {}), ...(options.body ? {'Content-Type': contentType || 'application/json'} : {}), ...(requestKey ? {'Idempotency-Key': requestKey} : {})}});
      const data = await response.json();
      if (!response.ok) {
        const message = response.status === 401 ? '이 기기의 연결을 확인해주세요.' : response.status === 409 ? '이전 전송과 요청 정보가 충돌했습니다. 내용을 확인해주세요.' : response.status === 413 ? '요청은 256 KiB 이하로 작성해주세요.' : '요청을 처리하지 못했습니다. HTTP ' + response.status;
        const error = new Error(message); error.status = response.status; throw error;
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('응답 시간이 초과됐습니다. 전송 요청이었다면 내용을 바꾸지 않고 다시 눌러주세요.');
      if (error instanceof TypeError) throw new Error('서버 연결을 확인해주세요. 전송 요청이었다면 내용을 바꾸지 않고 다시 눌러주세요.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function displayAuth(connected) {
    state.connected = connected;
    $('connect-form').classList.toggle('hidden', connected);
    $('disconnect').classList.toggle('hidden', !connected);
    $('composer').disabled = !(connected || state.publicSend) || state.sending;
    $('refresh').disabled = !connected;
    $('auth-heading').textContent = connected ? '이 브라우저는 자동으로 연결됩니다' : '새 기기 연결';
    $('auth-description').textContent = connected ? '30일 동안 키 입력 없이 이용할 수 있습니다. 공유 기기에서는 연결을 해제해주세요.' : '처음 한 번만 연결하면 이후에는 인증키를 입력하지 않아도 됩니다.';
    document.querySelector('.compose-footer > span').textContent = connected ? '접수한 메시지는 VM이 가져가 전달합니다.' : '기기를 연결하면 바로 전송할 수 있어요.';
    document.querySelector('.stats').classList.toggle('hidden', state.publicSend && !connected);
    document.querySelector('.history-panel').classList.toggle('hidden', state.publicSend && !connected);
    $('admin-access').open = !state.publicSend && !connected;
    if (state.publicSend && !connected) document.querySelector('.compose-footer > span').textContent = '누구나 키 없이 문장만 보내면 됩니다.';
    badge(connected ? '관리자 연결됨' : (state.publicSend ? '키 없이 전송 가능' : '연결 전'), connected || state.publicSend);
  }
  function formatTime(seconds) {
    return new Intl.DateTimeFormat('ko-KR', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false}).format(new Date(seconds * 1000));
  }
  function renderHistory(data) {
    for (const key of ['total', 'pending', 'leased', 'acked']) $('stat-' + key).textContent = data.stats[key].toLocaleString('ko-KR');
    $('history-count').textContent = data.messages.length;
    const signature = JSON.stringify(data.messages);
    if (state.historySignature !== signature) {
    state.historySignature = signature;
    $('history-body').replaceChildren();
    for (const item of data.messages) {
      const tr = document.createElement('tr');
      const content = document.createElement('td');
      const preview = document.createElement('span'); preview.className = 'message-preview'; preview.textContent = item.preview || '(빈 데이터)';
      const ident = document.createElement('span'); ident.className = 'message-id'; ident.textContent = item.id;
      content.append(preview, ident);
      const status = document.createElement('td');
      const pill = document.createElement('span'); pill.className = 'status-pill ' + item.status; pill.textContent = labels[item.status] || item.status; status.append(pill);
      const when = document.createElement('td'); when.textContent = formatTime(item.created);
      const attempts = document.createElement('td'); attempts.textContent = item.attempts;
      const action = document.createElement('td'); const button = document.createElement('button');
      button.type = 'button'; button.className = 'detail-button'; button.textContent = '↗'; button.setAttribute('aria-label', item.id + ' 상세 보기');
      button.addEventListener('click', () => showDetail(item.id)); action.append(button);
      tr.append(content, status, when, attempts, action); $('history-body').append(tr);
    }
    }
    $('empty-state').classList.toggle('hidden', data.messages.length > 0);
    $('empty-state').querySelector('strong').textContent = '아직 보낸 메시지가 없어요';
    $('empty-state').querySelector('p').textContent = '첫 메시지를 보내면 여기에 전달 상태가 표시됩니다.';
    state.next = data.next_cursor;
    $('pagination').classList.toggle('hidden', !state.next && !state.before);
    $('next-page').disabled = !state.next;
    $('first-page').disabled = !state.before;
    $('refresh-status').textContent = '5초마다 자동 갱신 · ' + new Intl.DateTimeFormat('ko-KR', {hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false}).format(new Date()) + ' 확인';
  }
  async function refresh() {
    if (!state.connected || state.loading) return;
    const generation = state.generation;
    state.loading = true; $('refresh').disabled = true;
    try {
      const data = await api('/messages?limit=25' + (state.before ? '&before=' + state.before : ''));
      if (generation !== state.generation) return;
      renderHistory(data); badge('서버 연결됨', true);
    } catch (error) {
      if (generation !== state.generation) return;
      badge('갱신 실패'); $('refresh-status').textContent = '최근 갱신에 실패했습니다. 표시된 내역이 최신이 아닐 수 있어요.';
      notice(error.message, true);
      if (error.status === 401) disconnect();
    } finally {
      state.loading = false;
      $('refresh').disabled = !state.connected;
    }
  }
  function disconnect() {
    state.token = ''; state.before = null; state.next = null; state.historySignature = null; state.generation++;
    displayAuth(false); $('token').value = '';
    $('history-body').replaceChildren(); $('history-count').textContent = '0'; $('pagination').classList.add('hidden');
    for (const key of ['total', 'pending', 'leased', 'acked']) $('stat-' + key).textContent = '—';
    $('empty-state').classList.remove('hidden');
    $('empty-state').querySelector('strong').textContent = '연결하면 전송 내역이 표시됩니다';
    $('empty-state').querySelector('p').textContent = '이 기기를 한 번 연결해 시작하세요.';
    $('refresh-status').textContent = '연결 후 5초마다 상태를 확인합니다.';
    $('detail-dialog').close(); $('detail-content').textContent = ''; $('detail-meta').textContent = '';
  }
  $('connect-form').addEventListener('submit', async event => {
    event.preventDefault();
    state.token = $('token').value.trim(); state.generation++;
    $('connect-button').disabled = true; $('connect-button').textContent = '연결 중…';
    try {
      await api('/session', {method: 'POST', body: ''});
      state.token = '';
      const data = await api('/messages?limit=25');
      state.before = null; $('token').value = ''; displayAuth(true); renderHistory(data); notice('이 기기를 연결했습니다. 다음부터는 자동으로 연결됩니다.');
    } catch (error) {state.token = ''; displayAuth(false); notice(error.message, true);}
    finally {$('connect-button').disabled = false; $('connect-button').textContent = '연결';}
  });
  $('disconnect').addEventListener('click', async () => {
    $('disconnect').disabled = true;
    try {await api('/logout', {method: 'POST', body: ''}); disconnect(); notice('이 기기의 자동 연결을 해제했습니다.');}
    catch (error) {if (error.status === 401) {disconnect(); notice('기기 연결이 이미 만료됐습니다.');} else {notice('연결 해제에 실패했습니다. 다시 시도해주세요.', true);}}
    finally {$('disconnect').disabled = false;}
  });
  $('message').addEventListener('input', () => {$('char-count').textContent = $('message').value.length.toLocaleString('ko-KR') + '자';});
  $('send-form').addEventListener('submit', async event => {
    event.preventDefault(); if (!(state.connected || state.publicSend) || state.sending) return;
    const text = $('message').value;
    if (!text.trim()) {notice('전달할 내용을 입력해주세요.', true); return;}
    if (new TextEncoder().encode(JSON.stringify({message: text})).length > 262144) {notice('메시지는 256 KiB 이하로 작성해주세요.', true); return;}
    if (state.retryText !== text || !state.retryKey) {
      state.retryText = text; state.retryKey = crypto.randomUUID();
    }
    state.sending = true; $('composer').disabled = true; $('send-button').textContent = '전송 중…'; $('disconnect').disabled = true;
    try {
      const result = await api('/send', {method: 'POST', body: text, contentType: 'text/plain; charset=utf-8', requestKey: state.retryKey});
      notice(result.created ? (state.connected ? '메시지를 접수했습니다. 아래 내역에서 전달 상태를 확인하세요.' : '메시지를 접수했습니다. VM이 순서대로 가져갑니다.') : '이미 접수한 메시지입니다. 중복 전송하지 않았습니다.');
      $('message').value = ''; $('char-count').textContent = '0자'; state.retryText = null; state.retryKey = null; state.before = null;
      await refresh();
    } catch (error) {notice(error.message, true);}
    finally {state.sending = false; $('composer').disabled = !(state.connected || state.publicSend); $('send-button').textContent = 'VM으로 전송 ↗'; $('disconnect').disabled = false;}
  });
  async function showDetail(id) {
    const generation = state.generation;
    try {
      const data = await api('/messages/' + encodeURIComponent(id));
      if (generation !== state.generation) return;
      $('detail-meta').textContent = data.id + ' · ' + labels[data.status];
      $('detail-content').textContent = JSON.stringify(data, null, 2); $('detail-dialog').showModal();
    } catch (error) {notice(error.message, true);}
  }
  $('close-detail').addEventListener('click', () => $('detail-dialog').close());
  $('refresh').addEventListener('click', refresh);
  $('first-page').addEventListener('click', () => {if (!state.loading) {state.before = null; refresh();}});
  $('next-page').addEventListener('click', () => {if (!state.loading && state.next) {state.before = state.next; refresh();}});
  async function restoreSession() {
    $('connect-button').disabled = true; badge('자동 연결 확인 중');
    try {
      const config = await api('/config');
      state.publicSend = config.public_send; displayAuth(false);
      await api('/session'); displayAuth(true); await refresh();
    } catch (error) {
      displayAuth(false);
      if (error.status !== 401) notice(error.message, true);
    } finally {$('connect-button').disabled = false;}
  }
  restoreSession();
  setInterval(() => {if (!document.hidden) refresh();}, 5000);
})();
