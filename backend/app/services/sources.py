from __future__ import annotations
import json, os, re, shutil, subprocess, uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import httpx
from bs4 import BeautifulSoup

from ..config import settings
from ..db import db
from .indexer import index_bytes,index_repository,index_text

class SourceError(RuntimeError): pass

def _source(project_id:str,kind:str,name:str,uri:str,metadata:dict|None=None)->str:
    sid=str(uuid.uuid4())
    with db() as conn: conn.execute('INSERT INTO sources(id,project_id,kind,name,uri,metadata_json) VALUES(?,?,?,?,?,?)',(sid,project_id,kind,name,uri,json.dumps(metadata or {})))
    return sid

def _set_status(sid:str,status:str,metadata:dict|None=None)->None:
    with db() as conn: conn.execute('UPDATE sources SET status=?,metadata_json=? WHERE id=?',(status,json.dumps(metadata or {}),sid))

def list_sources(project_id:str)->list[dict]:
    with db() as conn: rows=conn.execute('SELECT * FROM sources WHERE project_id=? ORDER BY created_at DESC',(project_id,)).fetchall()
    out=[]
    for r in rows:
        d=dict(r);d['metadata']=json.loads(d.pop('metadata_json') or '{}');out.append(d)
    return out

def _safe_repo_name(url:str)->str:
    p=urlparse(url).path.rstrip('/').split('/')[-1] or 'repository';return re.sub(r'[^A-Za-z0-9_.-]+','-',p.removesuffix('.git'))

def ingest_github(project_id:str,url:str,branch:str|None=None,token:str|None=None)->dict:
    # Works for GitHub HTTPS/SSH repository URLs. The token is only used for the clone command and never persisted.
    name=_safe_repo_name(url);sid=_source(project_id,'github',name,url,{'branch':branch})
    dest=settings.repos_dir/project_id/name
    if dest.exists():shutil.rmtree(dest)
    clone_url=url;secret=token or settings.github_token
    if secret and url.startswith('https://github.com/'):
        clone_url=url.replace('https://github.com/',f'https://x-access-token:{secret}@github.com/',1)
    cmd=['git','clone','--depth','1']
    if branch:cmd+=['--branch',branch]
    cmd += [clone_url,str(dest)]
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=600)
        if p.returncode!=0:raise SourceError(re.sub(re.escape(secret),'***',p.stderr) if secret else p.stderr)
        result=index_repository(project_id,dest,sid);_set_status(sid,'ready',{'branch':branch,'root':str(dest),'commit':_git_commit(dest),**{k:v for k,v in result.items() if k!='documents'}})
        return {'source_id':sid,'kind':'github','name':name,'commit':_git_commit(dest),**result}
    except Exception as exc:
        _set_status(sid,'failed',{'error':str(exc)[:1000]});raise

def _git_commit(root:Path)->str|None:
    try:return subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True,timeout=5).strip()
    except Exception:return None

def _gdrive_info(url:str)->tuple[str,str]:
    patterns=[('folder',r'/folders/([\w-]+)'),('document',r'/document/d/([\w-]+)'),('spreadsheets',r'/spreadsheets/d/([\w-]+)'),('presentation',r'/presentation/d/([\w-]+)'),('file',r'/file/d/([\w-]+)'),('file',r'[?&]id=([\w-]+)')]
    for kind,p in patterns:
        m=re.search(p,url)
        if m:return kind,m.group(1)
    raise SourceError('Could not parse Google Drive file or folder id')

def _download_drive_file(client:httpx.Client,file_id:str,name:str|None,mime:str|None,token:str|None)->tuple[bytes,str,str]:
    headers={'Authorization':f'Bearer {token}'} if token else {}
    google_types={
        'application/vnd.google-apps.document':('application/vnd.openxmlformats-officedocument.wordprocessingml.document','docx'),
        'application/vnd.google-apps.presentation':('application/vnd.openxmlformats-officedocument.presentationml.presentation','pptx'),
        'application/vnd.google-apps.spreadsheet':('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','xlsx'),
    }
    if mime in google_types and token:
        export_mime,ext=google_types[mime];r=client.get(f'https://www.googleapis.com/drive/v3/files/{file_id}/export',params={'mimeType':export_mime},headers=headers);r.raise_for_status();return r.content,(name or file_id)+'.'+ext,export_mime
    r=client.get(f'https://drive.google.com/uc?export=download&id={file_id}',headers=headers);r.raise_for_status()
    ctype=r.headers.get('content-type','application/octet-stream').split(';')[0];disp=r.headers.get('content-disposition','');m=re.search(r'filename="?([^";]+)',disp,re.I);return r.content,(m.group(1) if m else name or f'gdrive-{file_id}'),ctype

def ingest_gdrive(project_id:str,url:str,access_token:str|None=None)->dict:
    kind,fid=_gdrive_info(url);token=access_token or settings.google_access_token;sid=_source(project_id,'gdrive',f'gdrive-{fid}',url,{'file_id':fid,'drive_kind':kind})
    try:
        with httpx.Client(follow_redirects=True,timeout=120) as client:
            if kind=='folder':
                if not token:raise SourceError('Google Drive folder import requires GOOGLE_DRIVE_ACCESS_TOKEN or an access token. Individual public/shared files can be imported without it.')
                headers={'Authorization':f'Bearer {token}'};resp=client.get('https://www.googleapis.com/drive/v3/files',params={'q':f"'{fid}' in parents and trashed=false",'fields':'files(id,name,mimeType,size)','pageSize':1000},headers=headers);resp.raise_for_status();files=resp.json().get('files',[]);indexed=[]
                for f in files[:500]:
                    if f.get('mimeType')=='application/vnd.google-apps.folder':continue
                    try:
                        data,name,mime=_download_drive_file(client,f['id'],f.get('name'),f.get('mimeType'),token);indexed.append(index_bytes(project_id=project_id,source_type='gdrive',source_name=name,data=data,source_uri=f'https://drive.google.com/file/d/{f["id"]}',mime_type=mime,source_id=sid,metadata={'file_id':f['id'],'folder_id':fid}))
                    except Exception as exc:indexed.append({'name':f.get('name'),'error':str(exc)[:300]})
                result={'source_id':sid,'kind':'gdrive-folder','files':len(indexed),'indexed':sum(1 for x in indexed if 'document_id' in x),'details':indexed[:50]};_set_status(sid,'ready',{'folder_id':fid,'files':len(files)});return result
            if kind=='document':download=f'https://docs.google.com/document/d/{fid}/export?format=docx';name=f'gdrive-{fid}.docx'
            elif kind=='presentation':download=f'https://docs.google.com/presentation/d/{fid}/export/pptx';name=f'gdrive-{fid}.pptx'
            elif kind=='spreadsheets':download=f'https://docs.google.com/spreadsheets/d/{fid}/export?format=xlsx';name=f'gdrive-{fid}.xlsx'
            else:
                data,name,mime=_download_drive_file(client,fid,None,None,token);result=index_bytes(project_id=project_id,source_type='gdrive',source_name=name,data=data,source_uri=url,mime_type=mime,source_id=sid,metadata={'file_id':fid});_set_status(sid,'ready',{'file_id':fid});return {'source_id':sid,'kind':'gdrive','name':name,**result}
            headers={'Authorization':f'Bearer {token}'} if token else {};r=client.get(download,headers=headers);r.raise_for_status();mime=r.headers.get('content-type','application/octet-stream').split(';')[0];result=index_bytes(project_id=project_id,source_type='gdrive',source_name=name,data=r.content,source_uri=url,mime_type=mime,source_id=sid,metadata={'file_id':fid,'drive_kind':kind});_set_status(sid,'ready',{'file_id':fid,'drive_kind':kind});return {'source_id':sid,'kind':'gdrive','name':name,**result}
    except Exception as exc:_set_status(sid,'failed',{'error':str(exc)[:1000]});raise

def ingest_web(project_id:str,url:str)->dict:
    sid=_source(project_id,'web',urlparse(url).netloc or 'web',url)
    try:
        with httpx.Client(follow_redirects=True,timeout=90,headers={'User-Agent':'SpartanStudyBuddy/2.0'}) as client:r=client.get(url);r.raise_for_status()
        ctype=r.headers.get('content-type','').split(';')[0]
        if ctype.startswith('application/pdf') or url.lower().endswith('.pdf'):
            name=Path(urlparse(str(r.url)).path).name or 'document.pdf';result=index_bytes(project_id=project_id,source_type='web',source_name=name,data=r.content,source_uri=url,mime_type=ctype,source_id=sid)
        else:
            soup=BeautifulSoup(r.text,'lxml')
            for t in soup(['script','style','nav','footer','noscript','aside']):t.decompose()
            title=(soup.title.string.strip() if soup.title and soup.title.string else url);text='\n'.join(x.strip() for x in soup.get_text('\n').splitlines() if x.strip());result=index_text(project_id=project_id,source_type='web',source_name=title,content=text,source_uri=url,mime_type=ctype,source_id=sid,metadata={'title':title})
        _set_status(sid,'ready');return {'source_id':sid,'kind':'web',**result}
    except Exception as exc:_set_status(sid,'failed',{'error':str(exc)[:1000]});raise

def ingest_uri(project_id:str,uri:str,kind:str='auto',branch:str|None=None,access_token:str|None=None)->dict:
    if kind=='auto':
        if 'github.com' in uri or uri.startswith('git@github.com'):kind='github'
        elif 'drive.google.com' in uri or 'docs.google.com' in uri:kind='gdrive'
        else:kind='web'
    if kind=='github':return ingest_github(project_id,uri,branch,access_token)
    if kind=='gdrive':return ingest_gdrive(project_id,uri,access_token)
    return ingest_web(project_id,uri)
