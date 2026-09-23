#!/usr/bin/env python3
from __future__ import annotations
import json, shutil, socket, subprocess, tempfile, time, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EXT=ROOT/'apps'/'chrome-extension'
manifest=json.loads((EXT/'manifest.json').read_text())
assert manifest['manifest_version']==3
assert manifest['background']['service_worker']=='service-worker.js'
assert (EXT/'service-worker.js').exists() and (EXT/'content.js').exists()
assert '<all_urls>' in manifest.get('host_permissions',[])
print('Chrome manifest contract: PASS')

browser=next((shutil.which(x) for x in ('google-chrome','chromium','chromium-browser') if shutil.which(x)),None)
if not browser:
    print('Chrome DOM content-script test: SKIP (Chrome/Chromium not installed)')
    raise SystemExit(0)

html='<html><body><main><p id="target">StudyBuddy should understand this engineering learning passage and let me ask about it.</p></main></body></html>'
url='data:text/html;charset=utf-8,'+urllib.parse.quote(html)
tmp=Path(tempfile.mkdtemp(prefix='spartan-chrome-test-'))
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0)); debug_port=sock.getsockname()[1]
profile=tmp/'profile'
cmd=[browser,'--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--remote-allow-origins=*',f'--user-data-dir={profile}',f'--remote-debugging-port={debug_port}',url]
proc=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
try:
    targets=None
    for _ in range(60):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{debug_port}/json/list',timeout=1) as r: targets=json.load(r)
            if targets: break
        except Exception: time.sleep(.2)
    assert targets, 'Chromium remote debugging did not start'
    page=next((x for x in targets if x.get('type')=='page'),None)
    assert page, f'test page target missing: {targets}'
    import websocket
    ws=websocket.create_connection(page['webSocketDebuggerUrl'],timeout=5,origin=f'http://127.0.0.1:{debug_port}')
    def send(expr):
        send.i=getattr(send,'i',0)+1
        ws.send(json.dumps({'id':send.i,'method':'Runtime.evaluate','params':{'expression':expr,'returnByValue':True,'awaitPromise':True}}))
        while True:
            msg=json.loads(ws.recv())
            if msg.get('id')==send.i:return msg
    # Wait for the data document to be ready.
    for _ in range(30):
        ready=send("Boolean(document.getElementById('target'))")
        if ready.get('result',{}).get('result',{}).get('value') is True: break
        time.sleep(.1)
    assert ready.get('result',{}).get('result',{}).get('value') is True, 'test document did not load'
    # Run the real content script in Chromium with only extension messaging stubbed.
    stub="globalThis.chrome={runtime:{sendMessage:async(m)=>m.type==='config'?({api:'http://127.0.0.1:8000',user:'u',project:'p',tracking:true}):({ok:true,answer:'test'})}};"
    content=(EXT/'content.js').read_text()
    res=send(stub+'\n'+content+'\ntrue')
    assert 'exceptionDetails' not in res.get('result',{}), res
    selected=send("const n=document.getElementById('target'); const r=document.createRange(); r.selectNodeContents(n); const s=getSelection(); s.removeAllRanges(); s.addRange(r); s.toString()")
    assert len(selected.get('result',{}).get('result',{}).get('value',''))>12, selected
    send("document.dispatchEvent(new MouseEvent('mouseup',{bubbles:true})); true")
    time.sleep(.3)
    res=send("Boolean(document.getElementById('spartan-selection-action'))")
    assert res.get('result',{}).get('result',{}).get('value') is True, f'content script did not inject selection action: {res}'
    ws.close(); print('Chrome content-script DOM behavior: PASS')
finally:
    proc.terminate()
    try: proc.wait(timeout=5)
    except subprocess.TimeoutExpired: proc.kill()
    shutil.rmtree(tmp,ignore_errors=True)
