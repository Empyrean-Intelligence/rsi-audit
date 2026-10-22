"""Can the agent see what it is graded against?

Every file is identified by its git blob hash, so a directory on disk and a git revision give the
same answer (read a revision when the checkout is impossible, e.g. Windows path limits). A grader
file whose content also sits in an agent-visible path is SHARED; if the grader path looks like a
held-out test, answer key or reference solution it is a LEAK.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import subprocess

SECRET = re.compile(
    r"(^|/)(hidden|held[_-]?out|solutions?|answers?|answer[_-]?keys?|expected|gold|ground[_-]?truth)(/|$)"
    r"|(^|/)(known_good[^/]*|reference_solution[^/]*|solve\.(sh|py))$",
    re.IGNORECASE,
)


def _blob(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def files_from_dir(root):
    out = {}
    for d, subdirs, names in os.walk(root):
        subdirs[:] = [s for s in subdirs if s != ".git"]
        for name in names:
            p = os.path.join(d, name)
            with open(p, "rb") as f:
                data = f.read()
            out[os.path.relpath(p, root).replace(os.sep, "/")] = (_blob(data), len(data))
    return out


def files_from_git(repo, rev="HEAD"):
    res = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "-l", "-z", rev],
                         capture_output=True, check=True)
    out = {}
    for rec in res.stdout.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, kind, sha, size = meta.split()
        if kind != b"blob":
            continue
        out[path.decode("utf-8", "surrogateescape")] = (sha.decode(), int(size) if size != b"-" else 0)
    return out


def _match(path, globs):
    return any(fnmatch.fnmatchcase(path, g) for g in globs)


def scan(files, grader, visible, tasks=None, min_bytes=1):
    """files: {path: (blob, size)}. grader/visible: globs relative to a task root (or the repo root
    when tasks is None). tasks: a glob for task directories, e.g. 'tasks/*'."""
    if tasks:
        roots = sorted({"/".join(p.split("/")[: tasks.count("/") + 1]) for p in files
                        if fnmatch.fnmatchcase("/".join(p.split("/")[: tasks.count("/") + 1]), tasks)})
    else:
        roots = [""]
    if not roots:
        raise ValueError("no task directories match %r" % tasks)
    findings = []
    n_grader = 0
    for root in roots:
        pre = root + "/" if root else ""
        local = {p[len(pre):]: v for p, v in files.items() if p.startswith(pre)}
        g = {p: v for p, v in local.items() if _match(p, grader) and v[1] >= min_bytes}
        vis = {}
        for p, v in local.items():
            if _match(p, visible) and v[1] >= min_bytes:
                vis.setdefault(v[0], []).append(p)
        n_grader += len(g)
        for p, (sha, size) in sorted(g.items()):
            for q in vis.get(sha, []):
                if q == p:
                    continue
                findings.append({"task": root, "grader_file": p, "visible_file": q, "bytes": size,
                                 "kind": "LEAK" if SECRET.search(p) else "SHARED"})
    if n_grader == 0:
        raise ValueError("no grader files matched %s; check the globs" % grader)
    leaks = [f for f in findings if f["kind"] == "LEAK"]
    return {"verdict": "LEAK" if leaks else "NO LEAK FOUND", "tasks": len(roots), "grader_files": n_grader,
            "leaks": leaks, "shared": [f for f in findings if f["kind"] == "SHARED"]}


def report(r, show_shared=5):
    out = ["Scanned %d task(s), %d grader file(s)." % (r["tasks"], r["grader_files"])]
    for f in r["leaks"]:
        out.append("  LEAK    %s%s  ==  %s" % (f["task"] + ": " if f["task"] else "", f["grader_file"], f["visible_file"]))
    out.append("%d grader file(s) with identical content in an agent-visible path that do not look secret "
               "(SHARED; often harness code given on purpose -- read them):" % len(r["shared"]))
    for f in r["shared"][:show_shared]:
        out.append("  shared  %s%s  ==  %s" % (f["task"] + ": " if f["task"] else "", f["grader_file"], f["visible_file"]))
    if len(r["shared"]) > show_shared:
        out.append("  ... %d more (use --json)" % (len(r["shared"]) - show_shared))
    out.append("VERDICT: %s" % r["verdict"])
    out.append("Note: content matching only. A leak through a different encoding, a network path or a "
               "mount the globs do not cover is not seen; NO LEAK FOUND is not a proof of isolation.")
    return "\n".join(out)
