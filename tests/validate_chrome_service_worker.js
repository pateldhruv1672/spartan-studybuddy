const fs=require('fs');
const vm=require('vm');
const assert=require('assert');
let listener=null;
const chrome={
  storage:{local:{get:async(defaults)=>({...defaults,api:'http://spark.local:8000',user:'u1',project:'p1',tracking:true})}},
  runtime:{onMessage:{addListener:(fn)=>{listener=fn}}}
};
const fetch=async(url,opts)=>({ok:true,json:async()=>({ok:true,url,method:opts?.method||'GET'}),text:async()=>''});
const ctx={chrome,fetch,console,setTimeout,clearTimeout,JSON,Error};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('apps/chrome-extension/service-worker.js','utf8'),ctx,{filename:'service-worker.js'});
assert(listener,'runtime.onMessage listener was not registered');
function send(msg){return new Promise((resolve,reject)=>{const ret=listener(msg,{},resolve);if(ret!==true)reject(new Error('listener must return true for async response'));setTimeout(()=>reject(new Error('response timeout')),1000)})}
(async()=>{
  const c=await send({type:'config'});assert.equal(c.project,'p1');assert.equal(c.user,'u1');
  const ask=await send({type:'ask',question:'what does this do?',mode:'qa'});assert.equal(ask.ok,true);assert(ask.url.endsWith('/api/ask'));
  const ev=await send({type:'event',event:{type:'resource.opened',context:{title:'Docs'}}});assert.equal(ev.ok,true);assert(ev.url.endsWith('/api/events'));
  console.log('Chrome service-worker message contract: PASS');
})().catch(e=>{console.error(e);process.exit(1)});
