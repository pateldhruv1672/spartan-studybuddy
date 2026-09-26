"""Structural facts pulled from a single file: imports, links, mentions, headings, manifest dependencies.

Pure functions (no DB, no network) so they are cheap to run at index time and easy to unit-test.
Facts are *evidence*, not conclusions: resolving an import to a file or a mention to a symbol happens in
`builder.py`, where the whole project is visible.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import PurePosixPath
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore

CAPS = {'imports': 120, 'imports_sub': 120, 'urls': 40, 'links': 40, 'headings': 80, 'mentions': 120, 'deps': 250, 'targets': 60}

EXT_LANG = {
    '.py': 'python', '.js': 'javascript', '.jsx': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript',
    '.ts': 'typescript', '.tsx': 'typescript', '.vue': 'javascript', '.svelte': 'javascript',
    '.java': 'java', '.kt': 'kotlin', '.scala': 'scala', '.go': 'go', '.rs': 'rust', '.rb': 'ruby',
    '.php': 'php', '.cs': 'csharp', '.c': 'c', '.h': 'c', '.cpp': 'cpp', '.hpp': 'cpp', '.swift': 'swift',
    '.sh': 'shell', '.sql': 'sql',
}
DOC_EXTS = {'.md', '.mdx', '.rst', '.txt', '.pdf', '.docx', '.pptx', '.xlsx', '.html', '.htm'}
CONFIG_EXTS = {'.json', '.yaml', '.yml', '.toml', '.xml', '.ini', '.cfg', '.env'}
NODE_BUILTINS = {
    'fs', 'path', 'http', 'https', 'os', 'crypto', 'util', 'events', 'stream', 'url', 'zlib', 'child_process',
    'buffer', 'assert', 'net', 'tls', 'dns', 'readline', 'process', 'timers', 'querystring', 'module', 'vm', 'cluster',
}
PY_STDLIB = set(getattr(sys, 'stdlib_module_names', ())) | {'__future__'}


def language_of(name: str) -> str | None:
    return EXT_LANG.get(PurePosixPath(name).suffix.lower())


def is_doc_name(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in DOC_EXTS


def is_test_path(path: str) -> bool:
    p = path.replace('\\', '/').lower()
    base = p.rsplit('/', 1)[-1]
    return (
        '/tests/' in '/' + p or '/test/' in '/' + p or '/__tests__/' in '/' + p or '/spec/' in '/' + p
        or base.startswith('test_') or base.endswith(('_test.py', '_test.go', '.test.ts', '.test.tsx', '.test.js', '.test.jsx', '.spec.ts', '.spec.tsx', '.spec.js'))
        or base.endswith(('test.java', 'tests.java', 'tests.cs', '_spec.rb'))
    )


def is_entry_path(path: str) -> bool:
    base = path.replace('\\', '/').rsplit('/', 1)[-1].lower()
    stem, _, ext = base.rpartition('.')
    if base.startswith('readme') or base in {'makefile', 'dockerfile', 'docker-compose.yml', 'docker-compose.yaml'}:
        return True
    return stem in {'main', 'app', 'index', '__main__', 'manage', 'server', 'cli'} and f'.{ext}' in EXT_LANG


# ---------- imports ---------------------------------------------------------------------------------------

def _python_imports(text: str) -> tuple[list[str], list[str]]:
    """(definite module specs, speculative submodule specs from `from pkg import name`)."""
    out: list[str] = []
    sub: list[str] = []
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        for m in re.finditer(r'^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))', text, re.M):
            out.append(m.group(1) or m.group(2))
        return out, sub
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = '.' * node.level + (node.module or '')
            out.append(base)
            for a in node.names:                       # `from pkg import submodule` may name a module
                if a.name != '*':
                    sub.append((base if base.endswith('.') or not base else base + '.') + a.name)
    return out, sub


_JS = [
    re.compile(r'''\bimport\s+(?:[^'"()]*?\sfrom\s+)?['"]([^'"]+)['"]'''),
    re.compile(r'''\bexport\s+[^'"()]*?\sfrom\s+['"]([^'"]+)['"]'''),
    re.compile(r'''\brequire\(\s*['"]([^'"]+)['"]\s*\)'''),
    re.compile(r'''\bimport\(\s*['"]([^'"]+)['"]\s*\)'''),
]


def _imports(text: str, lang: str | None) -> list[str]:
    out: list[str] = []
    if lang in {'javascript', 'typescript'}:
        for p in _JS:
            out.extend(p.findall(text))
    elif lang == 'go':
        for block in re.findall(r'import\s*\((.*?)\)', text, re.S):
            out.extend(re.findall(r'"([^"]+)"', block))
        out.extend(re.findall(r'^\s*import\s+(?:\w+\s+)?"([^"]+)"', text, re.M))
    elif lang in {'java', 'kotlin', 'scala'}:
        out.extend(m.rstrip('.*') for m in re.findall(r'^\s*import\s+(?:static\s+)?([\w.]+(?:\.\*)?)', text, re.M))
    elif lang == 'csharp':
        out.extend(re.findall(r'^\s*using\s+(?:static\s+)?([\w.]+)\s*;', text, re.M))
    elif lang == 'rust':
        out.extend(re.findall(r'^\s*(?:pub\s+)?use\s+([\w:]+)', text, re.M))
        out.extend('self::' + m for m in re.findall(r'^\s*(?:pub\s+)?mod\s+(\w+)\s*;', text, re.M))
        out.extend(re.findall(r'^\s*extern\s+crate\s+(\w+)', text, re.M))
    elif lang in {'c', 'cpp'}:
        out.extend(re.findall(r'^\s*#\s*include\s+"([^"]+)"', text, re.M))
    elif lang == 'ruby':
        out.extend('./' + m for m in re.findall(r'''^\s*require_relative\s+['"]([^'"]+)['"]''', text, re.M))
        out.extend(re.findall(r'''^\s*require\s+['"]([^'"]+)['"]''', text, re.M))
    elif lang == 'php':
        out.extend(re.findall(r'^\s*use\s+([\w\\]+)', text, re.M))
    return out


# ---------- documents ---------------------------------------------------------------------------------------

_URL = re.compile(r'https?://[^\s<>()\[\]"\'`]+')
_MDLINK = re.compile(r'(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
_TICK = re.compile(r'`([^`\n]{2,90})`')
_IDENT = re.compile(r'^[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*$')
_PATHLIKE = re.compile(r'^[\w./-]+\.[A-Za-z0-9]{1,6}$|^[\w.-]+/[\w./-]+$')


def _urls(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for u in _URL.findall(text):
        u = u.rstrip('.,;:!?\'"')
        if len(u) < 500:
            seen.setdefault(u, None)
    return list(seen)


def _headings(text: str) -> list[dict[str, Any]]:
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r'^(#{1,6})\s+(.+?)\s*#*\s*$', line)
        if m:
            out.append({'level': len(m.group(1)), 'text': m.group(2)[:160], 'line': i})
    return out


def _mentions(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for raw in _TICK.findall(text):
        tok = raw.strip()
        tok = re.sub(r'\(.*\)$', '', tok)                    # foo(x) -> foo
        tok = tok.lstrip('./') if tok.startswith('./') else tok
        if ' ' in tok or len(tok) < 3:
            continue
        if _PATHLIKE.match(tok) or (_IDENT.match(tok) and (len(tok) >= 4)):
            seen.setdefault(tok, None)
    return list(seen)


def _md_links(text: str) -> list[str]:
    out = []
    for target in _MDLINK.findall(text):
        t = target.split('#', 1)[0]
        if t and not re.match(r'^[a-z][a-z0-9+.-]*:', t, re.I):
            out.append(t)
    return out


# ---------- manifests / ops files --------------------------------------------------------------------------

def _req_name(line: str) -> str | None:
    line = line.split('#', 1)[0].strip()
    if not line or line.startswith(('-', '.', 'git+', 'http')):
        return None
    m = re.match(r'^([A-Za-z0-9][A-Za-z0-9_.\-]*)', line)
    return m.group(1).lower().replace('_', '-') if m else None


def _manifest(base: str, path: str, text: str) -> tuple[list[dict[str, str]], list[str], list[str]]:
    deps: list[dict[str, str]] = []
    targets: list[str] = []
    hints: list[str] = []
    low = base.lower()
    p = path.lower()
    try:
        if re.match(r'requirements.*\.txt$', low):
            hints.append('manifest')
            deps += [{'name': n, 'eco': 'pypi'} for n in filter(None, (_req_name(l) for l in text.splitlines()))]
        elif low == 'pyproject.toml' and tomllib:
            hints.append('manifest')
            data = tomllib.loads(text)
            proj = data.get('project', {})
            names = list(proj.get('dependencies', []))
            for group in proj.get('optional-dependencies', {}).values():
                names += group
            names += list(data.get('tool', {}).get('poetry', {}).get('dependencies', {}).keys())
            deps += [{'name': n, 'eco': 'pypi'} for n in filter(None, (_req_name(x) for x in names)) if n != 'python']
        elif low == 'package.json':
            hints.append('manifest')
            data = json.loads(text)
            for key in ('dependencies', 'devDependencies', 'peerDependencies'):
                deps += [{'name': n, 'eco': 'npm'} for n in (data.get(key) or {})]
            targets += [f'npm run {s}' for s in (data.get('scripts') or {})]
        elif low == 'go.mod':
            hints.append('manifest')
            deps += [{'name': m, 'eco': 'go'} for m in re.findall(r'^\s*(?:require\s+)?([\w.\-]+\.[\w.\-]+/[\w./\-]+)\s+v[\w.\-+]+', text, re.M)]
        elif low == 'cargo.toml' and tomllib:
            hints.append('manifest')
            data = tomllib.loads(text)
            for key in ('dependencies', 'dev-dependencies'):
                deps += [{'name': n, 'eco': 'cargo'} for n in (data.get(key) or {})]
        elif low == 'pom.xml':
            hints.append('manifest')
            deps += [{'name': f'{g}.{a}', 'eco': 'maven'} for g, a in re.findall(r'<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>', text)]
        elif low == 'gemfile':
            hints.append('manifest')
            deps += [{'name': n, 'eco': 'gem'} for n in re.findall(r'''^\s*gem\s+['"]([^'"]+)['"]''', text, re.M)]
        elif low.startswith('dockerfile') or low.endswith('.dockerfile'):
            hints.append('container')
            deps += [{'name': i.split(':')[0].split('@')[0], 'eco': 'image'} for i in re.findall(r'^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)', text, re.M | re.I) if i.lower() != 'scratch']
        elif low.startswith('docker-compose') and low.endswith(('.yml', '.yaml')):
            hints.append('container')
            deps += [{'name': i.split(':')[0].split('@')[0], 'eco': 'image'} for i in re.findall(r'''^\s*image:\s*['"]?([^\s'"#]+)''', text, re.M)]
        elif low == 'makefile':
            targets += [t for t in re.findall(r'^([A-Za-z0-9][A-Za-z0-9_.\-]*)\s*:(?!=)', text, re.M)]
        elif '.github/workflows/' in p and low.endswith(('.yml', '.yaml')):
            hints.append('ci')
            deps += [{'name': u, 'eco': 'action'} for u in re.findall(r'^\s*-?\s*uses:\s*([\w./\-]+)@', text, re.M)]
        elif low in {'.gitlab-ci.yml'}:
            hints.append('ci')
        elif low.endswith('.tf'):
            hints.append('iac')
            deps += [{'name': n, 'eco': 'terraform'} for n in re.findall(r'^\s*provider\s+"(\w+)"', text, re.M)]
        elif low.endswith(('.yml', '.yaml')) and re.search(r'^kind:\s*(Deployment|StatefulSet|Service|Ingress|CronJob)\b', text, re.M):
            hints.append('k8s')
    except Exception:
        pass  # a malformed manifest must never break indexing
    return deps, targets, hints


# ---------- public entry point ----------------------------------------------------------------------------

def extract_facts(text: str, source_name: str, language: str | None = None) -> dict[str, Any]:
    path = source_name.replace('\\', '/')
    base = path.rsplit('/', 1)[-1]
    ext = PurePosixPath(base).suffix.lower()
    lang = language_of(base) or (language if language in set(EXT_LANG.values()) else None)
    facts: dict[str, Any] = {'imports': [], 'urls': [], 'links': [], 'headings': [], 'mentions': [], 'deps': [], 'targets': [], 'hints': []}
    if is_test_path(path):
        facts['hints'].append('test')
    if is_entry_path(path):
        facts['hints'].append('entry')
    facts['imports_sub'] = []
    if lang == 'python':
        defs, subs = _python_imports(text)
        facts['imports'] = list(dict.fromkeys(defs))
        facts['imports_sub'] = list(dict.fromkeys(subs))
    elif lang:
        facts['imports'] = list(dict.fromkeys(_imports(text, lang)))
    if ext in {'.md', '.mdx', '.rst', '.txt', '.html', '.htm'} or (not lang and ext not in CONFIG_EXTS):
        facts['headings'] = _headings(text) if ext in {'.md', '.mdx'} or text.lstrip().startswith('#') else []
        facts['mentions'] = _mentions(text)
        facts['links'] = _md_links(text)
    facts['urls'] = _urls(text)
    deps, targets, hints = _manifest(base, path, text)
    facts['deps'], facts['targets'] = deps, targets
    facts['hints'] += hints
    for key, cap in CAPS.items():
        facts[key] = facts[key][:cap]
    facts['hints'] = list(dict.fromkeys(facts['hints']))
    return facts
