const defaults={api:'http://100.108.27.105:8001',user:'demo-spartan',project:'',token:'',tracking:true};
async function cfg(){return {...defaults,...await chrome.storage.local.get(defaults)}}
async function call(path,opts={}){const c=await cfg();if(!c.token)throw new Error('Add your StudyBuddy login token in the extension popup');const r=await fetch(c.api+path,{headers:{'Content-Type':'application/json','Authorization':`Bearer ${c.token}`,...(opts.headers||{})},...opts});if(!r.ok)throw new Error(await r.text());return r.json()}
// Tracking POSTs (session/event) were previously wrapped in a silent .catch(()=>{}) on the content
// script side -- an expired token, a down backend, or a stale un-reloaded extension all failed
// completely silently, with no way for anyone to tell tracking wasn't working versus "nothing to
// track yet". A small red toolbar badge surfaces the last failure directly; it clears on the next
// success, so it reflects current state, not a one-time error.
function trackingFailed(err){chrome.action.setBadgeText({text:'!'});chrome.action.setBadgeBackgroundColor({color:'#ff453a'});chrome.action.setTitle({title:`Spartan StudyBuddy -- tracking error: ${String(err&&err.message||err).slice(0,180)}`})}
function trackingOk(){chrome.action.setBadgeText({text:''});chrome.action.setTitle({title:'Spartan StudyBuddy'})}
chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{(async()=>{try{
  const c=await cfg();
  if(msg.type==='event'){if(!c.tracking)return sendResponse({ok:false,disabled:true});const body={...msg.event,user_id:c.user,project_id:c.project||null,source:'browser'};const r=await call('/api/events',{method:'POST',body:JSON.stringify(body)});trackingOk();sendResponse(r);return}
  if(msg.type==='session'){if(!c.tracking)return sendResponse({ok:false,disabled:true});const r=await call('/api/resource/session',{method:'POST',body:JSON.stringify({...msg.session,user_id:c.user,project_id:c.project||null})});trackingOk();sendResponse(r);return}
  if(msg.type==='ask'){sendResponse(await call('/api/ask',{method:'POST',body:JSON.stringify({user_id:c.user,project_id:c.project,question:msg.question,mode:msg.mode||'auto',current_code:null})}));return}
  if(msg.type==='config'){sendResponse(c);return}
}catch(e){
  if(msg.type==='event'||msg.type==='session')trackingFailed(e);
  sendResponse({ok:false,error:String(e.message||e)})
}})();return true});

// Live push for job completion (e.g. resource_scout curating a course) -- the backend already
// broadcasts {kind:'agent_job', job:{...}} on this same /ws/{user_id} the web app uses, so we just
// listen for it here and surface a native notification instead of the user having to keep the tab
// open to find out. MV3 service workers are killed after ~30s idle REGARDLESS of an open WebSocket
// (a well-known MV3 gotcha -- a pending network connection does not by itself count as "activity"
// that keeps the worker alive), and a resource_scout job realistically takes 5-15 minutes, so the
// worker is almost always already dead by the time a job actually completes and the backend tries
// to push it. onStartup/onInstalled alone only reconnect on browser launch or extension
// install/update, never on the routine mid-session eviction -- so a chrome.alarms tick (the
// standard way to keep an MV3 service worker responsive) is what actually revives this.
let ws=null,wsRetryMs=2000;
chrome.alarms.create('studybuddy-ws-keepalive',{periodInMinutes:0.4});
chrome.alarms.onAlarm.addListener((a)=>{if(a.name==='studybuddy-ws-keepalive')connectJobSocket()});
async function connectJobSocket(){
  const c=await cfg();
  if(!c.token||!c.user){setTimeout(connectJobSocket,10000);return}
  if(ws&&ws.readyState<=1)return; // already open or connecting
  const url=c.api.replace(/^http/,'ws')+`/ws/${encodeURIComponent(c.user)}?token=${encodeURIComponent(c.token)}`;
  try{ws=new WebSocket(url)}catch(e){setTimeout(connectJobSocket,wsRetryMs);return}
  ws.onopen=()=>{wsRetryMs=2000};
  ws.onmessage=(ev)=>{
    let data;try{data=JSON.parse(ev.data)}catch(e){return}
    if(data.kind!=='agent_job')return;
    const job=data.job||{};
    if(job.kind!=='resource_scout')return;
    if(job.status!=='completed')return;
    const count=(job.result&&job.result.resources&&job.result.resources.length)||0;
    if(!count)return;
    chrome.notifications.create('studybuddy-course-'+job.id,{
      type:'basic',iconUrl:'icon128.png',
      title:'Your course is ready',
      message:`Found ${count} resource${count===1?'':'s'} for your learning path. Open StudyBuddy to start.`,
    });
  };
  ws.onclose=ws.onerror=()=>{ws=null;setTimeout(connectJobSocket,wsRetryMs);wsRetryMs=Math.min(wsRetryMs*2,60000)};
}
chrome.runtime.onStartup.addListener(connectJobSocket);
chrome.runtime.onInstalled.addListener(connectJobSocket);
connectJobSocket();
