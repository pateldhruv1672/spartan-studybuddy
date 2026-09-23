const D={api:'http://127.0.0.1:8000',user:'demo-spartan',project:'',tracking:true};
(async()=>{
  const c={...D,...await chrome.storage.local.get(D)};
  api.value=c.api;user.value=c.user;tracking.checked=c.tracking;
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});title.textContent=tab?.title||'—';
  async function loadProjects(selected=c.project){
    state.style.background='#ff9f0a';project.innerHTML='<option value="">Choose a workspace…</option>';
    try{
      const r=await fetch((api.value.trim()||D.api)+'/api/projects');if(!r.ok)throw new Error('Backend unavailable');
      const items=await r.json();for(const p of items){const o=document.createElement('option');o.value=p.id;o.textContent=p.name;project.appendChild(o)}
      if(selected&&![...project.options].some(o=>o.value===selected)){const o=document.createElement('option');o.value=selected;o.textContent=`Saved workspace · ${selected.slice(0,8)}`;project.appendChild(o)}
      project.value=selected||items[0]?.id||'';state.style.background='#34c759';return items
    }catch{state.style.background='#ff453a';if(selected){const o=document.createElement('option');o.value=selected;o.textContent=`Saved workspace · ${selected.slice(0,8)}`;project.appendChild(o);project.value=selected}return []}
  }
  refresh.onclick=()=>loadProjects(project.value);
  save.onclick=async()=>{await chrome.storage.local.set({api:api.value.trim(),user:user.value.trim(),project:project.value,tracking:tracking.checked});save.textContent='Saved ✓';setTimeout(()=>save.textContent='Save connection',1200)};
  open.onclick=()=>chrome.tabs.create({url:(api.value.trim()||D.api)+'/'});
  api.addEventListener('change',()=>loadProjects(''));
  await loadProjects(c.project);
})();
