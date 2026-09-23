const defaults={api:'http://127.0.0.1:8000',user:'demo-spartan',project:'',tracking:true};
async function cfg(){return {...defaults,...await chrome.storage.local.get(defaults)}}
async function call(path,opts={}){const c=await cfg();const r=await fetch(c.api+path,{headers:{'Content-Type':'application/json',...(opts.headers||{})},...opts});if(!r.ok)throw new Error(await r.text());return r.json()}
chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{(async()=>{try{
  const c=await cfg();
  if(msg.type==='event'){if(!c.tracking)return sendResponse({ok:false,disabled:true});const body={...msg.event,user_id:c.user,project_id:c.project||null,source:'browser'};sendResponse(await call('/api/events',{method:'POST',body:JSON.stringify(body)}));return}
  if(msg.type==='session'){if(!c.tracking)return sendResponse({ok:false,disabled:true});sendResponse(await call('/api/resource/session',{method:'POST',body:JSON.stringify({...msg.session,user_id:c.user,project_id:c.project||null})}));return}
  if(msg.type==='ask'){sendResponse(await call('/api/ask',{method:'POST',body:JSON.stringify({user_id:c.user,project_id:c.project,question:msg.question,mode:msg.mode||'auto',current_code:null})}));return}
  if(msg.type==='config'){sendResponse(c);return}
}catch(e){sendResponse({ok:false,error:String(e.message||e)})}})();return true});
