(()=>{
  if(location.protocol==='chrome-extension:'||location.protocol==='chrome:'||location.protocol==='about:')return;
  let cfg=null,lastTick=Date.now(),activeSeconds=0,lastSent=0,lastPosition=0,duration=0,progress=0,concepts=[],summary='',watchedTranscript=[],maxScrollProgress=0;
  // Reading progress for non-video pages (articles/papers/blogs): the deepest scroll position
  // reached, as a fraction of scrollable height. Monotonic -- scrolling back up never lowers it,
  // matching how a progress bar should read ("how far you've gotten"), not "where you are now".
  function readingProgress(){
    const scrollable=Math.max(1,document.documentElement.scrollHeight-window.innerHeight);
    const current=Math.max(0,Math.min(1,window.scrollY/scrollable));
    if(current>maxScrollProgress)maxScrollProgress=current;
    return maxScrollProgress;
  }
  const pageTitle=()=>document.title.replace(/\s+-\s+YouTube$/,'').trim().slice(0,240);
  const isYoutube=()=>/youtube\.com$/.test(location.hostname)||/www\.youtube\.com$/.test(location.hostname);
  const isArxiv=()=>/arxiv\.org$/.test(location.hostname);
  // Substack sites are usually *.substack.com, but many run on custom domains that still serve
  // the platform's own meta tag -- check both so a writer's own domain is still recognized.
  const isSubstack=()=>/(^|\.)substack\.com$/.test(location.hostname)||!!document.querySelector('meta[property="og:site_name"][content="Substack"]');
  const isMedium=()=>/(^|\.)medium\.com$/.test(location.hostname)||!!document.querySelector('meta[name="generator"][content="Medium"]');
  const articleType=()=>isArxiv()?'research_paper':(isMedium()||isSubstack())?'article':null;
  function visibleText(){const sel=window.getSelection()?.toString().trim();if(sel)return sel.slice(0,7000);const nodes=[...document.querySelectorAll('article,main,[role="main"]')];const text=(nodes[0]?.innerText||document.body?.innerText||'').replace(/\s+/g,' ').trim();return text.slice(0,9000)}
  async function config(){if(cfg)return cfg;cfg=await chrome.runtime.sendMessage({type:'config'});return cfg}

  // Auto-pick-up login: the extension and the web app are separate browser contexts with no
  // bridge by default, so without this the token/user/project had to be copy-pasted into the
  // popup by hand. The web app already writes its own session to localStorage (spartan_token,
  // spartan_project) on this same page, and content scripts share that localStorage (unlike page
  // JS, which is isolated) -- so when this content script is running ON the configured StudyBuddy
  // app origin, pull the session straight from there instead. user_id is embedded in the token
  // itself (payload.sub in the base64 segment before the first '.'), so nothing else is needed.
  // Runs once on load and on a light poll, since the app is an SPA -- login doesn't reload the
  // page, so a one-shot check at content-script-injection time would usually run before login
  // ever happens.
  async function autoSyncAuth(){
    try{
      const stored=await chrome.storage.local.get({api:'http://100.108.27.105:8001',token:'',user:'',project:''});
      if(!stored.api||new URL(stored.api).origin!==location.origin)return;
      const token=localStorage.getItem('spartan_token');
      if(!token)return;
      // Backend encodes this with base64.urlsafe_b64encode(...).rstrip(b'='): -/_ instead of +//,
      // and padding stripped -- atob() needs both restored or it throws (silently, into the catch
      // below) on every real token.
      const seg=token.split('.')[0];
      const b64=seg.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-seg.length%4)%4);
      const sub=JSON.parse(atob(b64)).sub;
      if(!sub)return;
      const project=localStorage.getItem('spartan_project')||'';
      if(stored.token===token&&stored.user===sub&&stored.project===project)return;
      await chrome.storage.local.set({token,user:sub,project});
      cfg=null; // force config() to re-fetch instead of serving the stale cached copy
    }catch(e){/* best effort -- never block page tracking on this */}
  }
  autoSyncAuth();
  setInterval(autoSyncAuth,5000);
  function event(type,context={}){chrome.runtime.sendMessage({type:'event',event:{type,resource_id:location.href,context:{url:location.href,title:pageTitle(),...context}}}).catch(()=>{})}
  async function chromeAI(text){
    try{
      if(!('LanguageModel' in globalThis))return null;
      const availability=await LanguageModel.availability();if(!['available','readily'].includes(String(availability)))return null;
      const session=await LanguageModel.create({systemPrompt:'Extract learning context from a webpage. Never infer mastery. Return compact JSON with summary, concepts, difficulty.'});
      const schema={type:'object',properties:{summary:{type:'string'},concepts:{type:'array',items:{type:'string'}},difficulty:{type:'string'}},required:['summary','concepts','difficulty']};
      const raw=await session.prompt(`Title: ${pageTitle()}\nURL: ${location.href}\nText: ${text.slice(0,5000)}`,{responseConstraint:schema});session.destroy?.();return JSON.parse(raw)
    }catch{return null}
  }
  function captureYoutubeCaption(v){try{for(const track of [...(v.textTracks||[])]){for(const cue of [...(track.activeCues||[])]){const t=String(cue.text||'').replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim();if(t&&watchedTranscript[watchedTranscript.length-1]!==t)watchedTranscript.push(t)} }if(watchedTranscript.length>250)watchedTranscript=watchedTranscript.slice(-250)}catch{}}
  function transcriptFromDom(){try{return [...document.querySelectorAll('ytd-transcript-segment-renderer .segment-text, ytd-transcript-segment-renderer yt-formatted-string')].map(x=>x.textContent.trim()).filter(Boolean).join(' ').slice(0,9000)}catch{return ''}}
  function tick(){if(document.visibilityState==='visible'&&document.hasFocus()){activeSeconds+=(Date.now()-lastTick)/1000}lastTick=Date.now();if(isYoutube()){const v=document.querySelector('video');if(v){lastPosition=v.currentTime||0;duration=v.duration||0;progress=duration?Math.min(1,lastPosition/duration):0;captureYoutubeCaption(v)}}else{progress=readingProgress();lastPosition=window.scrollY}}
  async function flush(reason='heartbeat'){
    const c=await config();if(!c.tracking||activeSeconds<1)return;
    const now=Date.now();if(now-lastSent<8000&&reason==='heartbeat')return;lastSent=now;
    let text='';if(activeSeconds>20)text=isYoutube()?([watchedTranscript.join(' '),transcriptFromDom(),visibleText()].filter(Boolean).join(' ').slice(0,9000)):visibleText();
    if(!summary&&text&&activeSeconds>45){const ai=await chromeAI(text);if(ai){summary=ai.summary||'';concepts=ai.concepts||[]}}
    const type=isYoutube()?'youtube':(articleType()||'web');
    chrome.runtime.sendMessage({type:'session',session:{url:location.href,title:pageTitle(),resource_type:type,seconds_active:activeSeconds,progress,last_position:lastPosition,duration:duration||null,visible_text:text,concepts}}).catch(()=>{});activeSeconds=0;
  }
  // Never track the StudyBuddy app's own pages as a "resource" -- this content script matches
  // <all_urls>, which includes the app itself, and without this check every path/study page you
  // visit while using StudyBuddy showed up in your own resume feed as a resource titled "Spartan
  // StudyBuddy", crowding out the real videos/articles you were actually resuming (the dashboard
  // only shows the 3 most recent, so a couple of self-tracked app-page entries was enough to push
  // real resume cards out entirely).
  (async()=>{
    try{
      const stored=await chrome.storage.local.get({api:'http://100.108.27.105:8001'});
      if(stored.api&&new URL(stored.api).origin===location.origin)return;
    }catch(e){/* if we can't tell, default to tracking rather than silently dropping real resources */}
    document.addEventListener('visibilitychange',()=>{tick();if(document.hidden)flush('hidden')});window.addEventListener('beforeunload',()=>{tick();flush('unload')});setInterval(()=>{tick();flush()},30000);
    // Resume-card deep link for non-video pages: "#studybuddy-resume=0.42" -> scroll to that
    // fraction of the page once content has rendered. YouTube resumes via the native ?t= param
    // instead (set by the dashboard), so this only applies elsewhere.
    if(!isYoutube()){
      const m=location.hash.match(/studybuddy-resume=([\d.]+)/);
      if(m){
        const target=Math.max(0,Math.min(1,parseFloat(m[1])));
        let attempts=0;
        const tryScroll=()=>{attempts++;const scrollable=document.documentElement.scrollHeight-window.innerHeight;if(scrollable>200||attempts>10){window.scrollTo({top:target*Math.max(1,scrollable),behavior:'smooth'});maxScrollProgress=target}else{setTimeout(tryScroll,300)}};
        setTimeout(tryScroll,300)
      }
    }
    event('resource.opened',{resource_type:isYoutube()?'youtube':(articleType()||'web')});
    if(isYoutube()){const attach=()=>{const v=document.querySelector('video');if(!v)return false;['play','pause','ended','seeking'].forEach(ev=>v.addEventListener(ev,()=>{tick();event(`video.${ev}`,{position:v.currentTime,duration:v.duration});if(ev!=='play')flush(ev)}));return true};if(!attach()){const mo=new MutationObserver(()=>{if(attach())mo.disconnect()});mo.observe(document.documentElement,{subtree:true,childList:true})}}
  })();
  // Tiny opt-in selection action; it never reads form fields or passwords.
  document.addEventListener('mouseup',()=>{const s=window.getSelection()?.toString().trim();let old=document.getElementById('spartan-selection-action');old?.remove();if(!s||s.length<12||s.length>1500)return;const b=document.createElement('button');b.id='spartan-selection-action';b.textContent='✦ Ask StudyBuddy';b.onclick=async()=>{const r=await chrome.runtime.sendMessage({type:'ask',question:`Explain this in simple terms and connect it to my onboarding context:\n\n${s}`,mode:'explain'});b.textContent=r?.answer?String(r.answer).slice(0,160):'Open StudyBuddy';setTimeout(()=>b.remove(),7000)};document.body.appendChild(b);const rect=window.getSelection().getRangeAt(0).getBoundingClientRect();b.style.left=`${Math.min(innerWidth-180,Math.max(12,rect.left+scrollX))}px`;b.style.top=`${rect.bottom+scrollY+8}px`});
})();
