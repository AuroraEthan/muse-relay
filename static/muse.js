(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {user:null, mode:'signup', muses:[], selected:null, publicMuse:null, owner:false, refreshing:false, refreshAgain:false, cursor:null, pending:null, sending:false};
  const pathMatch = location.pathname.match(/^\/m\/(m_[a-f0-9]{32})\/?$/);
  const publicId = pathMatch && pathMatch[1];
  const show = (id, yes=true) => $(id).classList.toggle('hidden', !yes);
  function el(tag, text, cls) { const node=document.createElement(tag); if(text!==undefined) node.textContent=text; if(cls) node.className=cls; return node; }
  function notice(message, error=false) { $('notice').textContent=message; $('notice').classList.toggle('error',error); show('notice',Boolean(message)); }
  const errors = {
    invalid_credentials:'사용자 이름과 비밀번호를 확인해주세요.', username_unavailable:'이미 사용 중인 이름입니다.',
    username_lowercase_letters_digits_underscore_3_to_32:'사용자 이름은 영문 소문자·숫자·밑줄 3–32자로 입력해주세요.',
    password_12_to_128_characters:'비밀번호는 12–128자로 입력해주세요.', login_required:'로그인이 필요합니다.',
    rate_limit_try_again_later:'잠시 후 다시 시도해주세요. 요청이 너무 많습니다.', maximum_3_muses_per_account:'계정당 Muse는 최대 3개입니다.',
    muse_pending_limit_1000:'대기 메시지가 1,000개입니다. 연결된 기기가 처리한 뒤 다시 보내주세요.',
    muse_name_1_to_60_characters:'Muse 이름은 1–60자로 입력해주세요.', message_limit_16384_bytes:'문장은 UTF-8 기준 16KB까지 보낼 수 있습니다.',
    message_text_required:'전달할 문장을 입력해주세요.', muse_not_found:'Muse를 찾을 수 없습니다.', same_origin_required:'페이지를 새로고침한 뒤 다시 시도해주세요.'
  };
  async function api(path, {method='GET',body,plain=false,key}={}) {
    const headers={};
    if(body!==undefined) headers['Content-Type']=plain?'text/plain; charset=utf-8':'application/json';
    if(key) headers['Idempotency-Key']=key;
    let response;
    try { response=await fetch(path,{method,headers,credentials:'same-origin',body:body===undefined?undefined:(plain?body:JSON.stringify(body))}); }
    catch(_) { const error=new Error('서버 응답을 확인하지 못했습니다. 연결 상태를 확인해주세요.'); error.uncertain=true; throw error; }
    let result;
    try { result=await response.json(); } catch(_) { const error=new Error('서버 응답을 확인하지 못했습니다.');error.uncertain=true;throw error; }
    if(!response.ok) { const error=new Error(errors[result.error] || `요청 실패 (${response.status})`);error.status=response.status;error.uncertain=response.status>=500;throw error; }
    return result;
  }
  function date(time) { return time?new Date(time*1000).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'아직 없음'; }
  function deviceText(m) { return !m.device_connected?'기기 연결 대기':m.last_seen && Date.now()/1000-m.last_seen<45?'기기 온라인':'기기 응답 대기'; }
  const webUrl = id => `${location.origin}/m/${id}`;
  const apiUrl = id => `${location.origin}/api/muses/${id}/send`;
  function instructions(m) { return `[${m.name}에 문장 보내기]\nAPI 주소: ${apiUrl(m.id)}\n메서드: POST\nContent-Type: text/plain; charset=utf-8\n본문: 보내고 싶은 문장 그대로\n인증키·로그인·JSON·직접 만드는 ID 불필요 (공개 수신이 켜져 있을 때)\n\nJavaScript 예시:\nconst response = await fetch('${apiUrl(m.id)}', {\n  method: 'POST',\n  headers: {'Content-Type': 'text/plain; charset=utf-8'},\n  body: '작업 결과를 정리해서 알려줘.'\n});\nif (!response.ok) throw new Error('HTTP ' + response.status);\nconsole.log(await response.json());\n\n성공: HTTP 201, {"id":"msg-자동생성값","created":true}\n서버 접수 성공은 Muse 전달·작업 실행 완료를 뜻하지 않습니다.\n문장 최대16KB, 분당60건. 자동 재시도 시에는 같은 요청에만 같은 Idempotency-Key를 사용하세요.\n다른 Codex: 사용자가 보내달라고 요청한 문장을 위 API에 text/plain으로 POST하세요. 스킬 설치가 필요하지 않습니다.\n웹 전송: ${webUrl(m.id)}`; }
  async function copy(text) {
    try { await navigator.clipboard.writeText(text);notice('복사했습니다. 그대로 붙여넣어 사용하세요.'); }
    catch(_) { const box=$('message-detail');box.textContent=text;$('message-dialog').showModal();notice('자동 복사를 사용할 수 없어 내용을 열었습니다. 선택해서 복사해주세요.'); }
  }
  const connectCommand = `python3 muse_agent.py connect --server ${location.origin}`;
  $('connect-command').textContent = connectCommand;
  $('copy-connect').dataset.copy = connectCommand;
  document.querySelectorAll('[data-copy]').forEach(button=>button.addEventListener('click',()=>copy(button.dataset.copy)));
  function authMode(mode) { state.mode=mode;['signup','login'].forEach(name=>{$(name+'-tab').classList.toggle('selected',name===mode);$(name+'-tab').setAttribute('aria-pressed',String(name===mode));});$('password').autocomplete=mode==='signup'?'new-password':'current-password';$('auth-submit').textContent=mode==='signup'?'계정 만들고 시작하기 ↗':'로그인 ↗';show('auth-help',mode==='signup'); }
  $('signup-tab').addEventListener('click',()=>authMode('signup'));
  $('login-tab').addEventListener('click',()=>authMode('login'));
  $('auth-form').addEventListener('submit',async event=>{
    event.preventDefault();const button=$('auth-submit');button.disabled=true;notice('');
    try { const result=await api('/api/auth/'+state.mode,{method:'POST',body:{username:$('username').value.trim().toLowerCase(),password:$('password').value}});state.user=result.user;$('password').value='';await renderHome(); }
    catch(error){notice(error.message,true);}finally{button.disabled=false;}
  });
  $('signout').addEventListener('click',async()=>{try{await api('/api/auth/logout',{method:'POST',body:{}});location.assign('/');}catch(error){notice(error.message,true);}});
  async function renderHome() {
    show('welcome',!state.user);show('dashboard',Boolean(state.user));show('signout',Boolean(state.user));
    if(!state.user)return;
    $('account-label').textContent=state.user.username.toUpperCase()+' / WORKSPACE';
    const result=await api('/api/muses');state.muses=result.muses;renderCards();
    if(state.muses.length) await selectMuse(state.selected && state.muses.find(m=>m.id===state.selected.id)||state.muses[0]);
    else show('manage',false);
  }
  function renderCards() {
    const list=$('muse-cards');list.replaceChildren();show('empty-muses',state.muses.length===0);
    for(const m of state.muses){const card=el('button',undefined,'muse-card'+(state.selected?.id===m.id?' selected':''));card.type='button';card.setAttribute('aria-pressed',String(state.selected?.id===m.id));const head=el('div',undefined,'card-head');head.append(el('span','m↗','card-avatar'),el('span',m.public_send?'공개 수신':'소유자 전용','pill'));card.append(head,el('span',m.name,'card-name'));const meta=el('span',deviceText(m),'card-meta');card.append(meta);card.addEventListener('click',()=>selectMuse(m).catch(error=>notice(error.message,true)));list.append(card);}
  }
  $('create-form').addEventListener('submit',async event=>{
    event.preventDefault();const button=event.currentTarget.querySelector('button');button.disabled=true;
    try { const {muse}=await api('/api/muses',{method:'POST',body:{name:$('muse-name').value,public_send:$('new-public').checked}});$('muse-name').value='';state.selected=muse;await renderHome();notice('Muse를 만들었습니다. 이제 연결 프로그램과 코드로 기기를 연결하세요.'); }
    catch(error){notice(error.message,true);}finally{button.disabled=false;}
  });
  async function selectMuse(m) {
    state.selected=m;state.cursor=null;$('history').replaceChildren(el('div','전송 내역을 불러오는 중…','empty'));$('stats').replaceChildren();show('more-history',false);show('pair-code',false);$('pair-value').textContent='';show('manage');renderCards();renderManage();await refresh();
  }
  function renderManage(){const m=state.selected;$('manage-name').textContent=m.name;$('web-url').textContent=webUrl(m.id);$('api-url').textContent=apiUrl(m.id);$('open-public').href=webUrl(m.id);$('public-setting').checked=m.public_send;$('device-status').textContent=deviceText(m)+(m.last_seen?' · 최근 '+date(m.last_seen):'');$('revoke-device').disabled=!m.device_connected;}
  $('copy-web').addEventListener('click',()=>copy(webUrl(state.selected.id)));
  $('copy-api').addEventListener('click',()=>copy(apiUrl(state.selected.id)));
  $('copy-instructions').addEventListener('click',()=>copy(instructions(state.selected)));
  $('copy-pair').addEventListener('click',()=>copy($('pair-value').textContent));
  $('generate-pair').addEventListener('click',async()=>{
    const button=$('generate-pair');button.disabled=true;const mid=state.selected.id;
    try{const result=await api(`/api/muses/${mid}/pairing`,{method:'POST',body:{}});if(state.selected.id===mid){$('pair-value').textContent=result.code;show('pair-code');notice('10분 안에 기기에서 코드를 입력하세요. 이전에 발급한 미사용 코드는 무효화됩니다.');}}
    catch(error){notice(error.message,true);}finally{button.disabled=false;}
  });
  $('revoke-device').addEventListener('click',async()=>{
    if(!confirm('기기 연결과 미사용 연결 코드를 해제할까요? 대기 메시지는 보관됩니다.'))return;
    try{await api(`/api/muses/${state.selected.id}/device/revoke`,{method:'POST',body:{}});show('pair-code',false);await refresh();notice('기기 연결을 해제했습니다.');}catch(error){notice(error.message,true);}
  });
  $('save-settings').addEventListener('click',async()=>{const button=$('save-settings');button.disabled=true;const mid=state.selected.id;try{const {muse}=await api(`/api/muses/${mid}/settings`,{method:'POST',body:{public_send:$('public-setting').checked}});state.muses=state.muses.map(m=>m.id===muse.id?muse:m);if(state.selected.id===mid){state.selected=muse;renderManage();}renderCards();notice('공개 수신 설정을 저장했습니다.');}catch(error){notice(error.message,true);}finally{button.disabled=false;}});
  function appendHistory(messages, append=false) {
    const list=$('history');if(!append)list.replaceChildren();
    if(!messages.length&&!append){const empty=el('div','아직 받은 문장이 없습니다. 전송 페이지에서 첫 문장을 보내보세요.','empty');list.append(empty);}
    for(const m of messages){const row=el('div',undefined,'history-row');const text=el('div');text.append(el('div',m.preview,'history-preview'),el('div',m.id,'history-id'));const button=el('button','보기','quiet');button.addEventListener('click',async()=>{try{$('message-detail').textContent=JSON.stringify(await api(`/api/muses/${state.selected.id}/messages/${m.id}`),null,2);$('message-dialog').showModal();}catch(error){notice(error.message,true);}});row.append(text,el('span',{pending:'대기 중',leased:'기기 가져감',acked:'전달 완료'}[m.status],'status '+m.status),el('span',date(m.created),'history-date'),button);list.append(row);}
  }
  async function refresh(append=false) {
    if(!state.selected)return;if(state.refreshing){state.refreshAgain=true;return;}state.refreshing=true;const mid=state.selected.id;
    try{const [info,history]=await Promise.all([api('/api/muses/'+mid),api(`/api/muses/${mid}/messages`+(append&&state.cursor?'?before='+state.cursor:''))]);if(state.selected.id!==mid)return;
      state.selected=info.muse;state.muses=state.muses.map(m=>m.id===mid?info.muse:m);renderCards();
      // Keep unsaved public setting untouched during background polling.
      $('device-status').textContent=deviceText(info.muse)+(info.muse.last_seen?' · 최근 '+date(info.muse.last_seen):'');$('revoke-device').disabled=!info.muse.device_connected;
      $('stats').replaceChildren();for(const [key,label] of [['total','전체'],['pending','대기 중'],['leased','가져감'],['acked','전달 완료']]){const item=el('div',undefined,'stat');item.append(el('span',label),el('strong',String(history.stats[key])));$('stats').append(item);}
      appendHistory(history.messages,append);state.cursor=history.next_cursor;show('more-history',Boolean(state.cursor));$('history-meta').textContent='5초마다 자동 갱신 · '+new Date().toLocaleTimeString('ko-KR')+' 확인';
    }catch(error){notice(error.message,true);}finally{state.refreshing=false;if(state.refreshAgain){state.refreshAgain=false;refresh();}}
  }
  $('refresh-history').addEventListener('click',()=>refresh());$('more-history').addEventListener('click',()=>refresh(true));
  $('close-dialog').addEventListener('click',()=>$('message-dialog').close());
  function pendingSave(value){state.pending=value;try{if(value)sessionStorage.setItem('muse-pending:'+publicId,JSON.stringify(value));else sessionStorage.removeItem('muse-pending:'+publicId);}catch(_){} }
  function sendingState(){const pending=Boolean(state.pending);$('message').readOnly=pending;$('send-button').textContent=pending?'같은 요청 다시 확인 ↗':'Muse로 전송 ↗';$('send-button').disabled=state.sending||(!state.publicMuse?.public_send&&!state.owner);show('abandon-send',pending);}
  async function publicPage(){
    try{const {muse}=await api('/api/muses/'+publicId);state.publicMuse=muse;state.owner=Boolean(muse.created);show('public-page');$('public-name').textContent=muse.name+'에게 보내기';document.title=muse.name+' · Muse Relay';$('public-badge').textContent=muse.public_send?'누구나 키 없이 전송 가능':'소유자 전용';show('private-notice',!muse.public_send&&!state.owner);$('message').disabled=!muse.public_send&&!state.owner;
      try{const saved=JSON.parse(sessionStorage.getItem('muse-pending:'+publicId));if(saved&&typeof saved.text==='string'&&typeof saved.key==='string'){state.pending=saved;$('message').value=saved.text;notice('이전 전송의 응답을 확인하지 못했습니다. 같은 요청으로 다시 확인할 수 있습니다.');}}catch(_){}
      sendingState();byteCount();
    }catch(error){if(error.status===404)show('not-found');else notice(error.message,true);}
  }
  function byteCount(){$('byte-count').textContent=new TextEncoder().encode($('message').value).length.toLocaleString()+' / 16,384 bytes';}
  $('message').addEventListener('input',byteCount);
  $('send-form').addEventListener('submit',async event=>{
    event.preventDefault();if(state.sending)return;const text=state.pending?state.pending.text:$('message').value;
    if(!text.trim()){notice('전달할 문장을 입력해주세요.',true);return;}if(new TextEncoder().encode(text).length>16384){notice(errors.message_limit_16384_bytes,true);return;}
    if(!state.pending)pendingSave({text,key:crypto.randomUUID()});state.sending=true;sendingState();notice('');
    try{const result=await api(`/api/muses/${publicId}/send`,{method:'POST',body:state.pending.text,plain:true,key:state.pending.key});pendingSave(null);$('message').value='';byteCount();$('receipt').textContent=(result.created?'서버에 접수했습니다.':'이미 접수한 문장입니다. 중복 저장하지 않았습니다.')+'\n'+result.id+'\n기기가 순서대로 가져갑니다. 작업 실행 완료는 별도로 확인해주세요.';show('receipt');}
    catch(error){if(!error.uncertain&&error.status!==429){pendingSave(null);}notice(error.message+(state.pending?' 같은 요청으로 다시 확인하면 중복 저장되지 않습니다.':''),true);}
    finally{state.sending=false;sendingState();}
  });
  $('abandon-send').addEventListener('click',()=>{if(confirm('이전 문장이 이미 접수됐을 수 있습니다. 새 문장은 별도로 접수됩니다. 계속할까요?')){pendingSave(null);$('message').value='';sendingState();byteCount();notice('');}});
  $('public-copy-api').addEventListener('click',()=>copy(instructions(state.publicMuse)));
  async function start(){try{try{state.user=(await api('/api/auth/me')).user;}catch(error){if(error.status!==401)throw error;}show('signout',Boolean(state.user));if(publicId)await publicPage();else await renderHome();}catch(error){notice(error.message,true);}finally{show('loading',false);}}
  setInterval(()=>{if(!document.hidden&&state.user&&!publicId&&!$('manage').classList.contains('hidden'))refresh();},5000);
  start();
})();
