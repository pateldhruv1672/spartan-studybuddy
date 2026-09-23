#!/usr/bin/env python3
from pathlib import Path
import json, zipfile
ROOT=Path(__file__).resolve().parents[2]; src=ROOT/'apps'/'vscode-extension'; out=ROOT/'dist'/'extensions'/'spartan-studybuddy-vscode.vsix'; out.parent.mkdir(parents=True,exist_ok=True)
pkg=json.loads((src/'package.json').read_text())
manifest=f'''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="{pkg['name']}" Version="{pkg['version']}" Publisher="{pkg['publisher']}" />
    <DisplayName>{pkg['displayName']}</DisplayName>
    <Description xml:space="preserve">{pkg['description']}</Description>
    <Categories>Other</Categories>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code" /></Installation>
  <Dependencies />
  <Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" /></Assets>
</PackageManifest>'''
content='''<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="json" ContentType="application/json"/><Default Extension="js" ContentType="application/javascript"/>
 <Default Extension="md" ContentType="text/markdown"/><Default Extension="svg" ContentType="image/svg+xml"/>
 <Default Extension="vsixmanifest" ContentType="text/xml"/>
</Types>'''
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('extension.vsixmanifest',manifest); z.writestr('[Content_Types].xml',content)
    for p in src.rglob('*'):
        if p.is_file(): z.write(p,'extension/'+str(p.relative_to(src)))
print(out)
