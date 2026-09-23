#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; ext=ROOT/'apps'/'chrome-extension'
m=json.loads((ext/'manifest.json').read_text())
assert m['manifest_version']==3
assert m['background']['service_worker']=='service-worker.js'
assert '<all_urls>' in m['host_permissions']
for f in ['service-worker.js','content.js','popup.js','popup.html','popup.css','content.css']:
    assert (ext/f).exists(), f
print('Chrome Manifest V3 package contract: PASS')
