const {test}=require('node:test');
const assert=require('node:assert/strict');
const {ConnectionPrompts,buildConnectionPrompt}=require('../static/muse-setup.js');
const a={id:'m_'+'a'.repeat(32),connected_at:null};
const b={id:'m_'+'b'.repeat(32),connected_at:null};
const response=()=>({code:'0123456789ABCDEF',expires_in:600});
test('reuse valid code, replace after expiry and explicit regeneration',async()=>{
 let now=1000,calls=0;const p=new ConnectionPrompts(()=>now);const request=async()=>{calls++;return response();};
 const first=await p.issue(a,request);assert.equal((await p.issue(a,request)).code,first.code);assert.equal(calls,1);
 now+=600000;assert.equal(p.current(a),null);await p.issue(a,request);assert.equal(calls,2);
 await p.issue(a,request,true);assert.equal(calls,3);
});
test('concurrent copy shares one issuance and Muse records stay isolated',async()=>{
 const p=new ConnectionPrompts(()=>1000);let finish,calls=0;const request=()=>{calls++;return new Promise(r=>finish=r);};
 const one=p.issue(a,request),two=p.issue(a,request);assert.equal(calls,1);assert.equal(p.current(b),null);
 finish(response());assert.equal((await one).code,(await two).code);assert.equal(p.current(b),null);
});
test('connection changes and explicit revoke invalidate codes, including in-flight requests',async()=>{
 const p=new ConnectionPrompts(()=>1000);await p.issue(a,async()=>response());assert.equal(p.current({...a,connected_at:2}),null);
 let finish;const pending=p.issue(a,()=>new Promise(r=>finish=r));p.invalidate(a.id);finish(response());
 await assert.rejects(pending,/setup_changed/);assert.equal(p.current(a),null);
});
test('invalid server responses cannot produce usable pairing prompts',async()=>{
 for(const value of [{code:'bad',expires_in:600},{code:response().code,expires_in:Infinity},{code:response().code,expires_in:601}]){
  const p=new ConnectionPrompts(()=>1000);await assert.rejects(p.issue(a,async()=>value));assert.equal(p.current(a),null);
 }
});
test('ready prompt contains actual scoped connection data and real Python API',async()=>{
 const p=new ConnectionPrompts(()=>1000);const r=await p.issue(a,async()=>response());
 const text=buildConnectionPrompt('https://relay.example',a,r,1000);
 for(const needed of ['https://relay.example/downloads/muse-agent.zip',a.id,r.code,'muse_agent.connect','localhost','Muse','Meta AI','일회용'])assert.ok(text.includes(needed),needed);
 assert.ok(!text.includes('--code'));assert.ok(!text.includes('여기에'));
 assert.throws(()=>buildConnectionPrompt('https://relay.example',a,r,r.expiresAt),/expired/);
 assert.throws(()=>buildConnectionPrompt('https://evil.example/path',a,r,1000));
 assert.throws(()=>buildConnectionPrompt('https://relay.example',b,r,1000));
});
