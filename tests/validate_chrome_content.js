const fs=require('fs');
const vm=require('vm');
const assert=require('assert');
const listeners={};
const nodes=new Map();
const selection={
  toString:()=> 'Explain this selected engineering concept in simple terms',
  getRangeAt:()=>({getBoundingClientRect:()=>({left:20,bottom:40})})
};
const document={
  title:'Engineering Docs',visibilityState:'visible',
  body:{innerText:'Engineering documentation about retries and idempotency.',appendChild:(el)=>{nodes.set(el.id,el)}},
  addEventListener:(type,fn)=>{listeners[type]=fn},
  querySelectorAll:()=>[],querySelector:()=>null,
  getElementById:(id)=>nodes.get(id)||null,
  createElement:(tag)=>({tagName:tag.toUpperCase(),id:'',textContent:'',style:{},remove(){if(this.id)nodes.delete(this.id)}}),
  hasFocus:()=>true
};
const window={
  getSelection:()=>selection,
  addEventListener:(type,fn)=>{listeners['window:'+type]=fn}
};
const chrome={runtime:{sendMessage:async(msg)=>msg.type==='ask'?{answer:'A simple explanation'}:{ok:true}}};
const ctx={
  console,document,window,chrome,
  location:{protocol:'https:',hostname:'docs.example.com',href:'https://docs.example.com/retries'},
  innerWidth:1200,scrollX:0,scrollY:0,
  setInterval:()=>0,setTimeout,clearTimeout,
  Date,Promise,MutationObserver:function(){this.observe=()=>{};this.disconnect=()=>{}},
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('apps/chrome-extension/content.js','utf8'),ctx,{filename:'content.js'});
assert(listeners.mouseup,'mouseup selection handler missing');
listeners.mouseup();
const btn=nodes.get('spartan-selection-action');
assert(btn,'selection action button was not created');
assert.equal(btn.textContent,'✦ Ask StudyBuddy');
Promise.resolve(btn.onclick()).then(()=>{
  assert(btn.textContent.includes('simple explanation'),'selection action did not use StudyBuddy response');
  console.log('Chrome content-script selection contract: PASS');
}).catch(e=>{console.error(e);process.exit(1)});
