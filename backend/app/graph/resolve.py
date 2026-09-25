"""Resolve raw import specifiers to project files (or classify them as external / unresolved).

Resolution is heuristic and language-aware but never compiler-grade (the spec allows this, section 7). It is
conservative on purpose: an ambiguous single-word match is treated as *external* rather than producing a
wrong edge, because a wrong dependency edge misleads a newcomer more than a missing one.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import Iterable

from .facts import NODE_BUILTINS, PY_STDLIB

JS_EXTS = ('.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.vue', '.svelte', '.json', '.css')


@dataclass(frozen=True)
class FileRef:
    repo: str
    path: str        # posix path relative to the repo/workspace root
    lang: str | None


@dataclass(frozen=True)
class Resolution:
    kind: str                    # 'file' | 'dir' | 'external' | 'stdlib' | 'unresolved'
    target: str | None = None    # path (file/dir) or package name (external)
    repo: str | None = None


def _no_ext(path: str) -> str:
    return re.sub(r'\.[A-Za-z0-9]+$', '', path)


class ImportResolver:
    def __init__(self, files: Iterable[FileRef]):
        self.files = list(files)
        self.by_repo_path: dict[tuple[str, str], FileRef] = {(f.repo, f.path): f for f in self.files}
        self.sfx_noext: dict[str, list[FileRef]] = {}
        self.sfx_ext: dict[str, list[FileRef]] = {}
        self.dirs: dict[str, list[str]] = {}        # dir path -> [repo,...]
        for f in self.files:
            parts = f.path.split('/')
            for i in range(len(parts)):
                self.sfx_ext.setdefault('/'.join(parts[i:]), []).append(f)
            stem = _no_ext(f.path)
            if stem.endswith('/__init__') or stem.endswith('/index'):
                stem = stem.rsplit('/', 1)[0]
            sp = stem.split('/')
            for i in range(len(sp)):
                self.sfx_noext.setdefault('/'.join(sp[i:]), []).append(f)
            d = posixpath.dirname(f.path)
            if d:
                self.dirs.setdefault(d, [])
                if f.repo not in self.dirs[d]:
                    self.dirs[d].append(f.repo)

    # ---- helpers -------------------------------------------------------------------------------------
    def _pick(self, cands: list[FileRef], importer: FileRef, lang: str | None = None) -> FileRef | None:
        cands = [c for c in cands if c.path != importer.path or c.repo != importer.repo]
        if lang:
            same = [c for c in cands if c.lang == lang]
            cands = same or cands
        if not cands:
            return None
        same_repo = [c for c in cands if c.repo == importer.repo]
        cands = same_repo or cands

        def closeness(c: FileRef) -> tuple[int, int, str]:
            a, b = importer.path.split('/')[:-1], c.path.split('/')[:-1]
            common = 0
            for x, y in zip(a, b):
                if x != y:
                    break
                common += 1
            return (-common, len(c.path), c.path)

        return sorted(cands, key=closeness)[0]

    def _exists(self, repo: str, path: str) -> FileRef | None:
        return self.by_repo_path.get((repo, path))

    # ---- per-language ---------------------------------------------------------------------------------
    def resolve(self, importer: FileRef, spec: str) -> Resolution:
        lang = importer.lang
        spec = spec.strip()
        if not spec:
            return Resolution('unresolved')
        if lang == 'python':
            return self._python(importer, spec)
        if lang in {'javascript', 'typescript'}:
            return self._js(importer, spec)
        if lang == 'go':
            return self._go(importer, spec)
        if lang in {'java', 'kotlin', 'scala', 'csharp', 'php'}:
            return self._dotted(importer, spec.replace('\\', '.'))
        if lang == 'rust':
            return self._rust(importer, spec)
        if lang in {'c', 'cpp'}:
            return self._c(importer, spec)
        if lang == 'ruby':
            return self._ruby(importer, spec)
        return Resolution('unresolved')

    def _python(self, importer: FileRef, spec: str) -> Resolution:
        d = posixpath.dirname(importer.path)
        if spec.startswith('.'):
            level = len(spec) - len(spec.lstrip('.'))
            rest = spec[level:].replace('.', '/')
            base = d
            for _ in range(level - 1):
                base = posixpath.dirname(base)
            target = posixpath.join(base, rest) if rest else base
            for cand in (f'{target}.py', f'{target}/__init__.py'):
                hit = self._exists(importer.repo, cand)
                if hit and hit.path != importer.path:
                    return Resolution('file', hit.path, hit.repo)
            return Resolution('unresolved')
        top = spec.split('.')[0]
        slashed = spec.replace('.', '/')
        sibling = self._exists(importer.repo, posixpath.join(d, slashed + '.py')) or self._exists(importer.repo, posixpath.join(d, slashed, '__init__.py'))
        if sibling and sibling.path != importer.path:
            return Resolution('file', sibling.path, sibling.repo)
        if top in PY_STDLIB:
            return Resolution('stdlib', top)
        cands = self.sfx_noext.get(slashed, [])
        if cands and ('.' in spec or all('/' not in c.path for c in cands)):
            hit = self._pick([c for c in cands if c.lang == 'python'], importer)
            if hit:
                return Resolution('file', hit.path, hit.repo)
        return Resolution('external', top)

    def _js(self, importer: FileRef, spec: str) -> Resolution:
        spec = spec.split('?', 1)[0]
        if spec.startswith('node:'):
            return Resolution('stdlib', spec[5:])
        if spec.startswith(('./', '../')) or spec in {'.', '..'}:
            base = posixpath.normpath(posixpath.join(posixpath.dirname(importer.path), spec))
            return self._js_try(importer, base)
        if spec.startswith(('@/', '~/')):
            rest = spec[2:]
            for prefix in ('src/', ''):
                r = self._js_try(importer, prefix + rest, suffix_ok=True)
                if r.kind == 'file':
                    return r
            return Resolution('unresolved')
        parts = spec.split('/')
        name = '/'.join(parts[:2]) if spec.startswith('@') else parts[0]
        if name in NODE_BUILTINS:
            return Resolution('stdlib', name)
        return Resolution('external', name)

    def _js_try(self, importer: FileRef, base: str, suffix_ok: bool = False) -> Resolution:
        cands = [base] + [base + e for e in JS_EXTS] + [f'{base}/index{e}' for e in JS_EXTS]
        for c in cands:
            hit = self._exists(importer.repo, c)
            if hit and hit.path != importer.path:
                return Resolution('file', hit.path, hit.repo)
        if suffix_ok:
            for c in cands:
                hits = self.sfx_ext.get(c, [])
                hit = self._pick(hits, importer)
                if hit:
                    return Resolution('file', hit.path, hit.repo)
        return Resolution('unresolved')

    def _go(self, importer: FileRef, spec: str) -> Resolution:
        parts = spec.split('/')
        for k in range(min(len(parts), 4), 0, -1):
            suffix = '/'.join(parts[-k:])
            for d, repos in sorted(self.dirs.items(), key=lambda x: -len(x[0])):
                if (d == suffix or d.endswith('/' + suffix)) and (k >= 2 or d.split('/')[-1] == parts[-1]):
                    if importer.repo in repos and d != posixpath.dirname(importer.path):
                        return Resolution('dir', d, importer.repo)
        if '.' not in parts[0]:
            return Resolution('stdlib', parts[0])
        return Resolution('external', spec)

    def _dotted(self, importer: FileRef, spec: str) -> Resolution:
        parts = [p for p in re.split(r'[.\\]', spec) if p]
        for k in range(len(parts), 0, -1):
            cands = self.sfx_noext.get('/'.join(parts[:k]))
            if cands:
                same_lang = [c for c in cands if c.lang == importer.lang]
                hit = self._pick(same_lang, importer)
                if hit and (k >= 2 or len(same_lang) == 1):
                    return Resolution('file', hit.path, hit.repo)
        return Resolution('external', '.'.join(parts[:3]))

    def _rust(self, importer: FileRef, spec: str) -> Resolution:
        d = posixpath.dirname(importer.path)
        if spec.startswith('self::'):
            name = spec[6:].split('::')[0]
            for cand in (f'{d}/{name}.rs', f'{d}/{name}/mod.rs'):
                hit = self._exists(importer.repo, cand)
                if hit:
                    return Resolution('file', hit.path, hit.repo)
            return Resolution('unresolved')
        segs = [s for s in spec.split('::') if s and s not in {'crate', 'self', 'super'}]
        if not segs:
            return Resolution('unresolved')
        if spec.split('::')[0] in {'std', 'core', 'alloc'}:
            return Resolution('stdlib', 'std')
        for k in range(len(segs), 0, -1):
            cands = self.sfx_noext.get('/'.join(segs[:k]))
            hit = self._pick([c for c in cands or [] if c.lang == 'rust'], importer)
            if hit and (k >= 2 or spec.startswith('crate::')):
                return Resolution('file', hit.path, hit.repo)
        return Resolution('external', segs[0])

    def _c(self, importer: FileRef, spec: str) -> Resolution:
        rel = posixpath.normpath(posixpath.join(posixpath.dirname(importer.path), spec))
        hit = self._exists(importer.repo, rel)
        if hit:
            return Resolution('file', hit.path, hit.repo)
        hit = self._pick(self.sfx_ext.get(spec, []), importer)
        return Resolution('file', hit.path, hit.repo) if hit else Resolution('unresolved')

    def _ruby(self, importer: FileRef, spec: str) -> Resolution:
        if spec.startswith('./'):
            base = posixpath.normpath(posixpath.join(posixpath.dirname(importer.path), spec))
            hit = self._exists(importer.repo, base + '.rb')
            return Resolution('file', hit.path, hit.repo) if hit else Resolution('unresolved')
        hit = self._pick([c for c in self.sfx_noext.get(spec, []) if c.lang == 'ruby'], importer)
        return Resolution('file', hit.path, hit.repo) if hit else Resolution('external', spec.split('/')[0])
