"""Static documentation and provider evidence analysis; never executes source."""
import ast
import fnmatch
import os
import re
from pathlib import Path
from .phrases import SERIAL, NOSERIAL


def normalize(text):
    return re.sub(r"\s+", " ", text.lower().replace("n't", " not").replace("-", " "))


def claims(text):
    prose = []
    fence = None
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if match:
            mark = match.group(1)
            if fence is None:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence):
                fence = None
            continue
        if fence is None:
            prose.append(line)
    positive = negative = False
    for paragraph in re.split(r"\n\s*\n", "\n".join(prose)):
        text = normalize(paragraph)
        for phrase in NOSERIAL:
            pattern = r"\b" + re.escape(phrase) + r"\b"
            if re.search(pattern, text):
                negative = True
                text = re.sub(pattern, " ", text)
        positive |= any(re.search(r"\b" + re.escape(p) + r"\b", text) is not None for p in SERIAL)
    return positive, negative


def evidence(source):
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    imports = {}
    shadowed = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            shadowed.add(node.name)
        elif isinstance(node, ast.Import):
            for item in node.names:
                imports[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                imports[item.asname or item.name] = node.module + '.' + item.name
    def resolve(node):
        if isinstance(node, ast.Name):
            return None if node.id in shadowed else imports.get(node.id)
        if isinstance(node, ast.Attribute):
            base = resolve(node.value)
            return base + '.' + node.attr if base else None
        return None
    def route(node):
        if not isinstance(node, ast.Call):
            return False
        name = resolve(node.func)
        if not name:
            return False
        parts = name.split('.')
        return ((parts[0] == 'serial' and parts[-1] in ('Serial', 'serial_for_url')) or
                (parts[0] == 'serial_asyncio' and parts[-1] == 'create_serial_connection'))
    # Every transfer receiver bound to a provider result necessarily contains
    # an A/B/C call in this same module, so that call also establishes D.
    return any(route(node) for node in ast.walk(tree))


def audit(root, ignore=(), fail_on='HIGH'):
    root = Path(root)
    if not root.is_dir():
        raise ValueError('root must be an existing readable directory')
    if not os.access(root, os.R_OK | os.X_OK):
        raise ValueError('root is unreadable')
    positive = negative = prod = test = False
    scanned = 0
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink()
                         and not any(fnmatch.fnmatch((Path(directory) / d).relative_to(root).as_posix(), g) for g in ignore))
        for filename in sorted(files):
            path = Path(directory) / filename
            relative = path.relative_to(root)
            parts = relative.parts
            if path.is_symlink() or any(fnmatch.fnmatch(relative.as_posix(), g) for g in ignore):
                continue
            is_doc = relative.as_posix() == 'README.md' or ('docs' in parts[:-1] and path.suffix.lower() == '.md')
            is_test = 'tests' in parts[:-1] or filename.startswith('test_') or filename.endswith('_test.py')
            excluded = any(p in ('fixtures', 'docs', 'examples') for p in parts[:-1])
            if not is_doc and not (path.suffix == '.py' and not excluded):
                continue
            try:
                content = path.read_text(encoding='utf-8')
            except (OSError, UnicodeError) as exc:
                raise ValueError('cannot read ' + relative.as_posix()) from exc
            scanned += 1
            if is_doc:
                p, n = claims(content)
                positive |= p
                negative |= n
            elif evidence(content):
                if is_test:
                    test = True
                else:
                    prod = True
    findings = []
    if positive and not prod:
        findings.append(dict(rule='documented-serial-claim-false', severity='MEDIUM' if test else 'HIGH',
                             message='Documented wired port capability has evidence only in tests.' if test else 'Documented wired port capability lacks production evidence.'))
    if negative and prod:
        findings.append(dict(rule='documented-no-serial-claim-false', severity='HIGH',
                             message='Documented absence of wired port capability contradicts production evidence.'))
    failed = any(f['severity'] == 'HIGH' or fail_on == 'MEDIUM' for f in findings)
    return dict(verdict='FAIL' if failed else 'PASS', findings=findings, scanned_files=scanned)
