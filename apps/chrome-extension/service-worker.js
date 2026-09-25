const defaults={api:'http://100.108.27.105:8001',user:'demo-spartan',project:'',token:'',tracking:true};
async function cfg(){return {...defaults,...await chrome.storage.local.get(defaults)}}
async function call(path,opts={}){const c=await cfg();if(!c.token)throw new Error('Add your StudyBuddy login token in the extension popup');const r=await fetch(c.api+path,{headers:{'Content-Type':'application/json','Authorization':`Bearer ${c.token}`,...(opts.headers||{})},...opts});if(!r.ok)throw new Error(await r.text());return r.json()}
chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{(async()=>{try{
  const c=await cfg();
  if(msg.type==='event'){if(!c.tracking)return sendResponse({ok:false,disabled:true});const body={...msg.event,user_id:c.user,project_id:c.project||null,source:'browser'};sendResponse(await call('/api/events',{method:'POST',body:JSON.stringify(body)}));return}
  if(msg.type==='session'){if(!c.tracking)return sendResponse({ok:false,disabled:true});sendResponse(await call('/api/resource/session',{method:'POST',body:JSON.stringify({...msg.session,user_id:c.user,project_id:c.project||null})}));return}
  if(msg.type==='ask'){sendResponse(await call('/api/ask',{method:'POST',body:JSON.stringify({user_id:c.user,project_id:c.project,question:msg.question,mode:msg.mode||'auto',current_code:null})}));return}
  if(msg.type==='config'){sendResponse(c);return}
}catch(e){sendResponse({ok:false,error:String(e.message||e)})}})();return true});

// Live push for job completion (e.g. resource_scout curating a course) -- the backend already
// broadcasts {kind:'agent_job', job:{...}} on this same /ws/{user_id} the web app uses, so we just
// listen for it here and surface a native notification instead of the user having to keep the tab
// open to find out. MV3 service workers get killed after ~30s idle; an open WebSocket keeps this
// one alive while connected, and we just reconnect (with backoff) whenever it drops.
let ws=null,wsRetryMs=2000;
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
