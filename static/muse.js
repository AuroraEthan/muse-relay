(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {user:null, mode:'signup', muses:[], selected:null, publicMuse:null, owner:false, refreshing:false, refreshAgain:false, cursor:null, pending:null, sending:false};
  const connectionPrompts = new ConnectionPrompts();
  const setupJobs = new Set();
  let setupSelection = 0;
  let senderSecret = null;
  let senderMutation = 0;
  const senderJobs = new Set();
  const connectionTest = new RelayTest({getItem:key=>sessionStorage.getItem(key),setItem:(key,value)=>sessionStorage.setItem(key,value)});
  const pathMatch = location.pathname.match(/^\/m\/(m_[a-f0-9]{32})\/?$/);
  const publicId = pathMatch && pathMatch[1];
  const show = (id, yes=true) => $(id).classList.toggle('hidden', !yes);
  function el(tag, text, cls) { const node=document.createElement(tag); if(text!==undefined) node.textContent=text; if(cls) node.className=cls; return node; }
  function notice(message, error=false) { $('notice').textContent=message; $('notice').classList.toggle('error',error); show('notice',Boolean(message)); }
  const errors = {
    invalid_credentials:'사용자 이름과 비밀번호를 확인해주세요.', username_unavailable:'이미 사용 중인 이름입니다.',
    username_lowercase_letters_digits_underscore_3_to_32:'사용자 이름은 영문 소문자·숫자·밑줄 3–32자로 입력해주세요.',
    password_12_to_128_characters:'비밀번호는 12–128자로 입력해주세요.', login_required:'로그인이 필요합니다.',
    rate_limit_try_again_later:'잠시 후 다시 시도해주세요. 요청이 너무 많습니다.', maximum_3_muses_per_account:'계정당 수신함은 최대 3개입니다.',
    muse_pending_limit_1000:'대기 메시지가 1,000개입니다. 연결된 기기가 처리한 뒤 다시 보내주세요.',
    muse_name_1_to_60_characters:'수신함 이름은 1–60자로 입력해주세요.', message_limit_16384_bytes:'문장은 UTF-8 기준 16KB까지 보낼 수 있습니다.',
    message_text_required:'전달할 문장을 입력해주세요.', muse_not_found:'수신함을 찾을 수 없습니다.', same_origin_required:'페이지를 새로고침한 뒤 다시 시도해주세요.', invalid_sender_key:'송신 API 키가 없거나 유효하지 않습니다.', public_sending_removed:'공개 수신은 지원하지 않습니다.'
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
  const apiUrl = () => `${location.origin}/api/send`;
  function instructions(m, key) { return `[${m.name}에 문장 보내기]
API 주소: ${apiUrl()}
메서드: POST
Authorization: Bearer ${key}
Content-Type: text/plain; charset=utf-8
본문: 보내고 싶은 문장 그대로

서버가 API 키로 수신함을 찾고, 그 수신함에 연결된 Muse의 VM으로 전달합니다. Muse ID·JSON·직접 만드는 메시지 ID는 필요 없습니다.
이 키는 이 수신함으로 전송만 허용합니다. 공개 게시물이나 브라우저 프런트엔드 소스에 넣지 말고, 신뢰하는 송신 프로그램의 비밀 설정에 보관하세요.

JavaScript (서버 또는 신뢰하는 실행 환경):
const response = await fetch('${apiUrl()}', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer ' + process.env.MUSE_API_KEY,
    'Content-Type': 'text/plain; charset=utf-8'
  },
  body: '작업 결과를 정리해서 알려줘.'
});
if (!response.ok) throw new Error('HTTP ' + response.status);
console.log(await response.json());
위 키를 실행 환경의 MUSE_API_KEY에 저장하세요.

성공: HTTP 201, {"id":"msg-자동생성값","created":true}
HTTP 401: 키 누락·오류·교체·폐기. 소유자에게 유효한 송신 키를 받으세요.
서버 접수, localhost 수신기 ACK, Meta AI 읽기·실행은 서로 다릅니다.
문장 최대 16KB, 수신함당 분당 60건. 자동 재시도는 같은 본문과 같은 Idempotency-Key로 하세요. 키를 교체해도 수신함과 연결된 Muse는 바뀌지 않습니다.
다른 Codex: 사용자가 보내달라고 요청한 문장을 위 API로 POST하세요. 인증키는 Authorization 헤더에만 넣고 URL·본문·로그에는 출력하지 마세요. 스킬 설치는 필요하지 않습니다.`; }
  function clearSenderSecret() {
    senderSecret=null;$('sender-key').value='';$('sender-fallback').value='';show('sender-fallback-box',false);
  }
  function renderSender() {
    const m=state.selected;if(!m)return;
    const meta=m.sender_key||{active:false};
    if(senderSecret&&(senderSecret.mid!==m.id||senderSecret.version!==meta.version))clearSenderSecret();
    const available=Boolean(senderSecret);
    $('sender-key').value=available?senderSecret.key:'';
    $('sender-key-status').textContent=meta.active?`발급됨 · ${meta.prefix}… · ${date(meta.created)}`:'발급된 송신 키가 없습니다.';
    $('issue-sender-key').textContent=senderJobs.has(m.id)?'키 발급 확인 중…':meta.active?'송신 키 교체':'송신 API 키 발급';
    $('issue-sender-key').disabled=senderJobs.has(m.id);
    $('revoke-sender-key').disabled=!meta.active||senderJobs.has(m.id);
    $('copy-sender-key').disabled=!available||senderJobs.has(m.id);
    $('copy-instructions').disabled=!available||senderJobs.has(m.id);
    $('sender-key-help').textContent=available?'지금 키와 사용법을 복사해 안전하게 보관하세요. 페이지를 새로고침하거나 다른 수신함을 선택하면 원문을 다시 볼 수 없습니다.':'키 원문은 발급 직후에만 복사할 수 있습니다. 보관한 키를 잃어버리면 교체하세요. 기존 키는 교체 즉시 사용할 수 없습니다.';
  }
  async function copySender(text) {
    const mid=state.selected.id, epoch=setupSelection, secret=senderSecret, mutation=senderMutation;
    const unchanged=()=>state.selected?.id===mid&&setupSelection===epoch&&senderSecret===secret&&senderMutation===mutation;
    try{await navigator.clipboard.writeText(text);if(unchanged())notice('송신 정보를 복사했습니다. 신뢰하는 프로그램에만 전달하세요.');}
    catch(_){if(!unchanged()||!senderSecret)return;$('sender-fallback').value=text;show('sender-fallback-box');$('sender-fallback').focus();$('sender-fallback').select();notice('자동 복사가 차단됐습니다. 아래 선택된 내용을 복사하세요.');}
  }
  async function changeSender(revoke=false) {
    const m=state.selected;if(!m||senderJobs.has(m.id))return;
    if((revoke||m.sender_key?.active)&&!confirm(revoke?'송신 키를 폐기할까요? 이 키를 쓰는 프로그램은 즉시 전송할 수 없게 됩니다. Muse 연결과 기존 메시지는 유지됩니다.':'송신 키를 교체할까요? 기존 키를 쓰는 프로그램의 키도 바꿔야 합니다. Muse 연결은 유지됩니다.'))return;
    const mid=m.id,epoch=setupSelection;senderMutation++;senderJobs.add(mid);clearSenderSecret();renderSender();
    try {
      const result=await api(`/api/muses/${mid}/sender-key${revoke?'/revoke':''}`,{method:'POST',body:{}});
      const meta=revoke?{active:false}:result.sender_key;
      state.muses=state.muses.map(item=>item.id===mid?{...item,sender_key:meta}:item);
      if(state.selected?.id!==mid||setupSelection!==epoch){notice('송신 키 변경을 완료했습니다. 해당 수신함을 다시 선택해 상태를 확인하세요. 키 원문을 보관하지 못했다면 교체하세요.');return;}
      state.selected={...state.selected,sender_key:meta};
      if(!revoke)senderSecret={mid,key:result.key,version:meta.version};
      notice(revoke?'송신 키를 폐기했습니다.':'송신 API 키를 발급했습니다. 지금 복사해 보관하세요.');
    }catch(error){if(state.selected?.id===mid&&setupSelection===epoch)notice(error.message+(error.uncertain?' 키 변경이 반영됐을 수 있습니다. 상태를 확인하고 원문을 받지 못했다면 다시 교체하세요.':''),true);}
    finally{senderMutation++;senderJobs.delete(mid);if(state.selected?.id===mid&&setupSelection===epoch){renderSender();refresh();}}
  }
  $('issue-sender-key').addEventListener('click',()=>changeSender());
  $('revoke-sender-key').addEventListener('click',()=>changeSender(true));
  $('copy-sender-key').addEventListener('click',()=>{if(senderSecret)copySender(senderSecret.key);});
  async function copy(text) {
    try { await navigator.clipboard.writeText(text);notice('복사했습니다. 그대로 붙여넣어 사용하세요.'); }
    catch(_) { const box=$('message-detail');box.textContent=text;$('message-dialog').showModal();notice('자동 복사를 사용할 수 없어 내용을 열었습니다. 선택해서 복사해주세요.'); }
  }
  const connectCommand = `python3 muse_agent.py connect --server ${location.origin}`;
  $('connect-command').textContent = connectCommand;
  $('copy-connect').dataset.copy = connectCommand;
  document.querySelectorAll('[data-copy]').forEach(button=>button.addEventListener('click',()=>copy(button.dataset.copy)));
  function authMode(mode) { state.mode=mode;['signup','login'].forEach(name=>{$(name+'-tab').classList.toggle('selected',name===mode);$(name+'-tab').setAttribute('aria-pressed',String(name===mode));});$('password').autocomplete=mode==='signup'?'new-password':'current-password';$('auth-submit').textContent=mode==='signup'?'계정 만들고 시작하기 ↗':'로그인 ↗';show('auth-help',mode==='signup'); }
  function revealAuth() {
    if(publicId||state.user)return;
    const mode=location.hash==='#login'?'login':location.hash==='#signup'?'signup':null;
    show('auth-section',Boolean(mode));
    if(mode){authMode(mode);requestAnimationFrame(()=>{$('auth-section').scrollIntoView({block:'start'});$('username').focus({preventScroll:true});});}
  }
  window.addEventListener('hashchange',revealAuth);
  $('signup-tab').addEventListener('click',()=>authMode('signup'));
  $('login-tab').addEventListener('click',()=>authMode('login'));
  $('auth-form').addEventListener('submit',async event=>{
    event.preventDefault();const button=$('auth-submit');button.disabled=true;notice('');
    try { const result=await api('/api/auth/'+state.mode,{method:'POST',body:{username:$('username').value.trim().toLowerCase(),password:$('password').value}});state.user=result.user;$('password').value='';await renderHome(); }
    catch(error){notice(error.message,true);}finally{button.disabled=false;}
  });
  $('signout').addEventListener('click',async()=>{try{await api('/api/auth/logout',{method:'POST',body:{}});location.assign('/');}catch(error){notice(error.message,true);}});
  async function renderHome() {
    show('welcome',!state.user);show('dashboard',Boolean(state.user));show('signout',Boolean(state.user));show('nav-login',!state.user);show('nav-start',!state.user);
    if(!state.user){revealAuth();return;}
    $('account-label').textContent=state.user.username.toUpperCase()+' / WORKSPACE';
    const result=await api('/api/muses');state.muses=result.muses;renderCards();
    if(state.muses.length) await selectMuse(state.selected && state.muses.find(m=>m.id===state.selected.id)||state.muses[0]);
    else show('manage',false);
  }
  function renderCards() {
    const list=$('muse-cards');list.replaceChildren();show('empty-muses',state.muses.length===0);
    for(const m of state.muses){const card=el('button',undefined,'muse-card'+(state.selected?.id===m.id?' selected':''));card.type='button';card.setAttribute('aria-pressed',String(state.selected?.id===m.id));const head=el('div',undefined,'card-head');head.append(el('span','m↗','card-avatar'),el('span','API 키 인증','pill'));card.append(head,el('span',m.name,'card-name'));const meta=el('span',deviceText(m),'card-meta');card.append(meta);card.addEventListener('click',()=>selectMuse(m).catch(error=>notice(error.message,true)));list.append(card);}
  }
  $('create-form').addEventListener('submit',async event=>{
    event.preventDefault();const button=event.currentTarget.querySelector('button');button.disabled=true;
    try { const {muse}=await api('/api/muses',{method:'POST',body:{name:$('muse-name').value}});$('muse-name').value='';state.selected=muse;await renderHome();notice('수신함을 만들었습니다. 연결 프롬프트를 복사해 Muse 대화에 붙여넣으세요.');$('copy-muse-prompt').focus(); }
    catch(error){notice(error.message,true);}finally{button.disabled=false;}
  });
  async function selectMuse(m) {
    setupSelection++;clearSenderSecret();state.selected=m;state.cursor=null;$('history').replaceChildren(el('div','전송 내역을 불러오는 중…','empty'));$('stats').replaceChildren();show('more-history',false);show('pair-code',false);$('pair-value').textContent='';show('manage');renderCards();renderManage();await refresh();
  }
  function renderManage(){const m=state.selected;$('manage-name').textContent=m.name;$('web-url').textContent=webUrl(m.id);$('api-url').textContent=apiUrl(m.id);$('open-public').href=webUrl(m.id);$('device-status').textContent=deviceText(m)+(m.last_seen?' · 최근 '+date(m.last_seen):'');$('revoke-device').disabled=!m.device_connected;renderOnboarding();renderSetup();renderSender();}
  function renderOnboarding(){
    const m=state.selected;if(!m)return;const test=connectionTest.read(m.id);
    const checks=[['수신함 만들기',true],['VM 연결',m.device_connected],['테스트 문장 접수',Boolean(test.messageId)],['수신기 ACK',test.status==='acked']];
    $('onboarding-list').replaceChildren(...checks.map(([label,done],i)=>el('li',(done?'✓':String(i+1).padStart(2,'0'))+'  '+label,done?'done':'')));
    $('send-test').disabled=test.busy;
    $('send-test').textContent=test.busy?'접수 확인 중…':test.pending?'같은 테스트 다시 확인 ↗':test.messageId&&test.status!=='acked'?'새 테스트 문장 보내기 ↗':'테스트 문장 보내기 ↗';
    $('test-status').textContent=test.busy?'테스트 문장의 접수를 확인하는 중입니다…':test.pending?'접수 결과를 확인하지 못했습니다.':test.status==='acked'?'이 테스트 문장의 localhost 수신기 도착 확인 ✓':test.messageId?'테스트 문장을 접수했습니다. 수신기 ACK 대기 중.':'테스트 문장을 아직 보내지 않았습니다.';
    $('test-detail').textContent=test.pending?'같은 키와 문장으로 다시 확인합니다. 중복 접수를 막습니다.':test.messageId?test.messageId+' · '+(test.status==='acked'?'이 ID의 수신 기록입니다. 새 기기를 연결했다면 새 테스트를 보내세요. Meta AI의 읽기·실행은 별도로 확인하세요.':'기기 온라인이어도 수신기가 응답할 때까지 기다립니다.'):'버튼을 누를 때만 선택한 수신함으로 테스트 문장을 보냅니다.';
  }
  $('send-test').addEventListener('click',async()=>{
    if(!state.selected)return;const mid=state.selected.id;
    const promise=connectionTest.send(mid,request=>api(`/api/muses/${mid}/send`,{method:'POST',body:request.text,plain:true,key:request.key}));renderOnboarding();
    try{await promise;if(state.selected.id===mid)await refresh();}
    catch(error){if(state.selected.id===mid)notice(error.message,true);}
    finally{if(state.selected.id===mid)renderOnboarding();}
  });
  function renderSetup() {
    const muse=state.selected;if(!muse)return;
    const record=connectionPrompts.current(muse);
    const busy=setupJobs.has(muse.id);
    $('copy-muse-prompt').disabled=busy;$('generate-pair').disabled=busy;
    $('copy-muse-prompt').textContent=busy?'프롬프트 준비 중…':record?'연결 프롬프트 다시 복사 ↗':'연결 프롬프트 만들고 복사 ↗';
    show('setup-ready',Boolean(record));show('pair-code',Boolean(record));
    if(record){
      const text=buildConnectionPrompt(location.origin,muse,record);
      if($('setup-prompt').value!==text)$('setup-prompt').value=text;
      $('pair-value').textContent=record.code;
      const seconds=Math.max(0,Math.ceil((record.expiresAt-Date.now())/1000));
      $('setup-status').textContent=`Muse에 붙여넣기 · 유효 시간 ${Math.floor(seconds/60)}분 ${seconds%60}초 · 일회용`;
    }else{
      $('setup-prompt').value='';$('pair-value').textContent='';$('setup-preview').open=false;
      $('setup-status').textContent=busy?'선택한 수신함의 연결 정보를 준비하고 있습니다.':muse.device_connected?'VM이 연결되어 있습니다. 다시 연결할 때만 새 프롬프트를 만드세요.':'유효한 프롬프트가 없습니다. 새로 만들어 Muse에게 전달하세요.';
    }
  }
  async function copySetupText(text,muse,record) {
    if(state.selected.id!==muse.id||connectionPrompts.current(state.selected)!==record)return;
    try{await navigator.clipboard.writeText(text);notice('복사했습니다. 10분 안에 연결할 Muse 대화에 붙여넣으세요.');}
    catch(_){
      if(state.selected.id!==muse.id||connectionPrompts.current(state.selected)!==record){renderSetup();return;}
      renderSetup();$('setup-preview').open=true;$('setup-prompt').focus();$('setup-prompt').select();
      notice('자동 복사를 사용할 수 없어 프롬프트를 열었습니다. 선택된 전체 내용을 복사해 Muse에게 전달하세요.');
    }
  }
  async function prepareSetup(copyIt,force=false) {
    if(!state.selected)return;
    const muse=state.selected,mid=muse.id,selection=setupSelection;
    if(setupJobs.has(mid))return;
    setupJobs.add(mid);renderSetup();notice('');
    try{
      const record=await connectionPrompts.issue(muse,()=>api(`/api/muses/${mid}/pairing`,{method:'POST',body:{}}),force);
      if(state.selected.id!==mid||setupSelection!==selection)return;
      if(connectionPrompts.current(state.selected)!==record)throw new Error('setup_changed');
      renderSetup();
      if(copyIt)await copySetupText(buildConnectionPrompt(location.origin,state.selected,record),muse,record);
      else notice('새 프롬프트를 만들었습니다. 이전 미사용 코드는 무효화됐습니다. 복사해 Muse에게 붙여넣으세요.');
    }catch(error){
      if(state.selected.id===mid&&setupSelection===selection)notice(['setup_changed','pairing_expired'].includes(error.message)?'연결 상태가 바뀌었거나 코드가 만료됐습니다. 새 프롬프트를 만들어주세요.':error.message,true);
    }finally{setupJobs.delete(mid);if(state.selected.id===mid)renderSetup();}
  }
  $('copy-muse-prompt').addEventListener('click',()=>prepareSetup(true));
  $('select-setup-prompt').addEventListener('click',()=>{
    if(!connectionPrompts.current(state.selected)){renderSetup();notice('코드가 만료됐습니다. 새 프롬프트를 만들어주세요.',true);return;}
    $('setup-prompt').focus();$('setup-prompt').select();
  });
  $('copy-web').addEventListener('click',()=>copy(webUrl(state.selected.id)));
  $('copy-api').addEventListener('click',()=>copy(apiUrl(state.selected.id)));
  $('copy-instructions').addEventListener('click',()=>{if(senderSecret)copySender(instructions(state.selected,senderSecret.key));});
  $('copy-pair').addEventListener('click',()=>{const muse=state.selected,record=connectionPrompts.current(muse);if(record)copySetupText(record.code,muse,record);else renderSetup();});
  $('generate-pair').addEventListener('click',()=>prepareSetup(false,true));
  $('revoke-device').addEventListener('click',async()=>{
    if(!state.selected||!confirm('기기 연결과 미사용 연결 코드를 해제할까요? 대기 메시지는 보관됩니다.'))return;
    const mid=state.selected.id;
    try{await api(`/api/muses/${mid}/device/revoke`,{method:'POST',body:{}});connectionPrompts.invalidate(mid);if(state.selected.id===mid){renderSetup();await refresh();notice('기기 연결을 해제했습니다.');}}catch(error){if(state.selected.id===mid)notice(error.message,true);}
  });
  function appendHistory(messages, append=false) {
    const list=$('history');if(!append)list.replaceChildren();
    if(!messages.length&&!append){const empty=el('div','아직 받은 문장이 없습니다. 전송 페이지에서 첫 문장을 보내보세요.','empty');list.append(empty);}
    for(const m of messages){const row=el('div',undefined,'history-row');const text=el('div');text.append(el('div',m.preview,'history-preview'),el('div',m.id,'history-id'));const button=el('button','보기','quiet');button.addEventListener('click',async()=>{try{$('message-detail').textContent=JSON.stringify(await api(`/api/muses/${state.selected.id}/messages/${m.id}`),null,2);$('message-dialog').showModal();}catch(error){notice(error.message,true);}});row.append(text,el('span',{pending:'대기 중',leased:'기기 가져감',acked:'수신기 ACK'}[m.status],'status '+m.status),el('span',date(m.created),'history-date'),button);list.append(row);}
  }
  async function refresh(append=false) {
    if(!state.selected)return;if(state.refreshing){state.refreshAgain=true;return;}state.refreshing=true;const mid=state.selected.id;const senderVersion=senderMutation;
    try{const [info,history]=await Promise.all([api('/api/muses/'+mid),api(`/api/muses/${mid}/messages`+(append&&state.cursor?'?before='+state.cursor:''))]);if(state.selected.id!==mid)return;
      if(senderVersion!==senderMutation||senderJobs.has(mid))info.muse.sender_key=state.selected.sender_key;
      state.selected=info.muse;renderSender();state.muses=state.muses.map(m=>m.id===mid?info.muse:m);renderCards();
      $('device-status').textContent=deviceText(info.muse)+(info.muse.last_seen?' · 최근 '+date(info.muse.last_seen):'');$('revoke-device').disabled=!info.muse.device_connected;
      $('stats').replaceChildren();for(const [key,label] of [['total','전체'],['pending','대기 중'],['leased','가져감'],['acked','수신기 ACK']]){const item=el('div',undefined,'stat');item.append(el('span',label),el('strong',String(history.stats[key])));$('stats').append(item);}
      const test=connectionTest.read(mid);let testLookupError=false;
      if(test.messageId){
        try{const message=await api(`/api/muses/${mid}/messages/${test.messageId}`);connectionTest.observe(mid,message);}
        catch(error){testLookupError=true;}
      }
      if(state.selected.id!==mid)return;renderOnboarding();renderSetup();
      if(testLookupError)$('test-detail').textContent=test.messageId+' · 현재 수신 상태를 확인하지 못했습니다. 다음 갱신에서 다시 확인합니다.';
      appendHistory(history.messages,append);state.cursor=history.next_cursor;show('more-history',Boolean(state.cursor));$('history-meta').textContent='5초마다 자동 갱신 · '+new Date().toLocaleTimeString('ko-KR')+' 확인';
    }catch(error){notice(error.message,true);}finally{state.refreshing=false;if(state.refreshAgain){state.refreshAgain=false;refresh();}}
  }
  $('refresh-history').addEventListener('click',()=>refresh());$('more-history').addEventListener('click',()=>refresh(true));
  $('close-dialog').addEventListener('click',()=>$('message-dialog').close());
  function pendingSave(value){state.pending=value;try{if(value)sessionStorage.setItem('muse-pending:'+publicId,JSON.stringify(value));else sessionStorage.removeItem('muse-pending:'+publicId);}catch(_){} }
  function sendingState(){const pending=Boolean(state.pending);$('message').readOnly=pending;$('send-button').textContent=pending?'같은 요청 다시 확인 ↗':'Muse로 전송 ↗';$('send-button').disabled=state.sending||!state.owner;show('abandon-send',pending);}
  async function publicPage(){
    try{const {muse}=await api('/api/muses/'+publicId);state.publicMuse=muse;state.owner=Boolean(muse.created);show('public-page');$('public-name').textContent=muse.name+' 수신함';document.title=muse.name+' · Muse Relay';$('public-badge').textContent='소유자 전용';show('private-notice',!state.owner);$('message').disabled=!state.owner;
      try{const saved=JSON.parse(sessionStorage.getItem('muse-pending:'+publicId));if(saved&&typeof saved.text==='string'&&typeof saved.key==='string'){state.pending=saved;$('message').value=saved.text;notice('이전 전송의 응답을 확인하지 못했습니다. 같은 요청으로 다시 확인할 수 있습니다.');}}catch(_){}
      sendingState();byteCount();
    }catch(error){if(error.status===401){show('public-page');show('private-notice');$('public-badge').textContent='소유자 로그인 필요';$('message').disabled=true;sendingState();}else if(error.status===404)show('not-found');else notice(error.message,true);}
  }
  function byteCount(){$('byte-count').textContent=new TextEncoder().encode($('message').value).length.toLocaleString()+' / 16,384 bytes';}
  $('message').addEventListener('input',byteCount);
  $('send-form').addEventListener('submit',async event=>{
    event.preventDefault();if(state.sending)return;const text=state.pending?state.pending.text:$('message').value;
    if(!text.trim()){notice('전달할 문장을 입력해주세요.',true);return;}if(new TextEncoder().encode(text).length>16384){notice(errors.message_limit_16384_bytes,true);return;}
    if(!state.pending)pendingSave({text,key:crypto.randomUUID()});state.sending=true;sendingState();notice('');
    try{const result=await api(`/api/muses/${publicId}/send`,{method:'POST',body:state.pending.text,plain:true,key:state.pending.key});pendingSave(null);$('message').value='';byteCount();$('receipt').textContent=(result.created?'서버에 접수했습니다.':'이미 접수한 문장입니다. 중복 저장하지 않았습니다.')+'\n'+result.id+'\n서버 접수 ≠ localhost 수신기 ACK ≠ Meta AI 실행. 수신기 ACK는 소유자의 관리 화면에서, Meta AI의 읽기·실행은 Muse의 VM 환경에서 확인하세요.';show('receipt');}
    catch(error){if(!error.uncertain&&error.status!==429){pendingSave(null);}notice(error.message+(state.pending?' 같은 요청으로 다시 확인하면 중복 저장되지 않습니다.':''),true);}
    finally{state.sending=false;sendingState();}
  });
  $('abandon-send').addEventListener('click',()=>{if(confirm('이전 문장이 이미 접수됐을 수 있습니다. 새 문장은 별도로 접수됩니다. 계속할까요?')){pendingSave(null);$('message').value='';sendingState();byteCount();notice('');}});
  async function start(){try{try{state.user=(await api('/api/auth/me')).user;}catch(error){if(error.status!==401)throw error;}show('signout',Boolean(state.user));show('nav-login',!state.user);show('nav-start',!state.user);if(publicId)await publicPage();else await renderHome();}catch(error){notice(error.message,true);}finally{show('loading',false);}}
  setInterval(()=>{if(!document.hidden&&state.user&&!publicId&&!$('manage').classList.contains('hidden'))refresh();},5000);
  setInterval(()=>{if(!document.hidden&&state.selected&&!publicId)renderSetup();},1000);
  start();
})();
