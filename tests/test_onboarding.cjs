const {test}=require('node:test');
const assert=require('node:assert/strict');
const {RelayTest}=require('../static/muse-test.js');
function fixture(){const data=new Map();return new RelayTest({getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)},()=> 'unique-key');}
test('uncertain and rate limited sends reuse exact text and key; definite rejection clears pending',async()=>{
 const t=fixture();let first;const fail=async request=>{first??=request;assert.deepEqual(request,first);throw Object.assign(new Error('retry'),{uncertain:true});};
 await assert.rejects(t.send('a',fail));await assert.rejects(t.send('a',fail));
 await assert.rejects(t.send('a',async request=>{assert.deepEqual(request,first);throw {status:429};}));assert.deepEqual(t.read('a').pending,first);
 await assert.rejects(t.send('a',async()=>{throw {status:400};}));assert.equal(t.read('a').pending,null);
});
test('only exact returned message ACK confirms test, per Muse and across reload',async()=>{
 const data=new Map();const storage={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)};const t=new RelayTest(storage,()=> 'key');
 await t.send('a',async()=>({id:'test-a'}));t.observe('a',{id:'older',status:'acked'});assert.notEqual(t.read('a').status,'acked');
 t.observe('a',{id:'test-a',status:'leased'});assert.equal(t.read('a').status,'leased');assert.equal(t.read('b').messageId,null);
 const reloaded=new RelayTest(storage);assert.equal(reloaded.read('a').messageId,'test-a');reloaded.observe('a',{id:'test-a',status:'acked'});assert.equal(reloaded.read('a').status,'acked');
});
test('double click sends once and in-flight result stays with captured Muse',async()=>{
 const t=fixture();let finish;let calls=0;const send=()=>{calls++;return new Promise(r=>finish=r);};const a=t.send('a',send);await t.send('a',send);assert.equal(calls,1);assert.equal(t.read('a').busy,true);assert.equal(t.read('b').busy,false);finish({id:'a-id'});await a;assert.equal(t.read('a').messageId,'a-id');assert.equal(t.read('b').messageId,null);
});
test('starting a new test replaces prior ACK immediately, including uncertain outcomes',async()=>{
 const t=fixture();await t.send('a',async()=>({id:'old'}));t.observe('a',{id:'old',status:'acked'});
 let fail;const next=t.send('a',()=>new Promise((_,reject)=>fail=reject));assert.equal(t.read('a').messageId,null);assert.equal(t.read('a').status,null);
 fail({uncertain:true});await assert.rejects(next);assert.equal(t.read('a').status,null);
});
