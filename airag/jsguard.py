"""Loop guards for generated JavaScript (interactive explainers).

A generated script with an endless loop would freeze the whole app: on phones the explainer frame runs on the
same thread as AIRAG's own page. Like code playgrounds do, every braced `for`, `while` and `do` loop gets a
guard at the start of its body. A heartbeat timer runs while the page is responsive; if a loop keeps the page
busy for more than 2 seconds, the guard breaks out of it (and of the loops around it), and the explainer shows
a short note instead of hanging.

The scanner understands strings, template literals, comments and regular expressions, so code inside those is
never changed. Loops without braces are left alone (rare in generated code).
"""
from __future__ import annotations

import re
from typing import List, Tuple

GUARD_CALL = "if(__airagGuard())break;"

PRELUDE = (
    "<script>(function(){var last=performance.now(),n=0,tripped=false,told=false;"
    "setInterval(function(){last=performance.now();tripped=false;},250);"
    "window.__airagGuard=function(){if(tripped)return true;if((++n&1023)!==0)return false;"
    "if(performance.now()-last>2000){tripped=true;if(!told){told=true;setTimeout(function(){try{"
    "var d=document.createElement('div');d.textContent='Part of this explainer ran too long and was stopped.';"
    "d.style.cssText='position:fixed;left:8px;bottom:8px;padding:6px 10px;border-radius:8px;background:#222;"
    "color:#fff;font:12px sans-serif;z-index:2147483647';document.body.appendChild(d);}catch(e){}},0);}"
    "return true;}return false;};})();</script>"
)

_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
# after these, a "/" starts a regular expression (not a division)
_REGEX_AFTER_WORDS = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw",
                      "instanceof", "yield", "await"}


def _tokens(code: str) -> List[Tuple[str, int, int]]:
    """(kind, start, end) for the code-level tokens: 'id', 'p' (punctuation) and 'x' (string/comment/regex)."""
    out: List[Tuple[str, int, int]] = []
    i, n = 0, len(code)
    while i < n:
        c = code[i]
        if c.isspace():
            i += 1
            continue
        if code.startswith("//", i):
            j = code.find("\n", i)
            j = n if j < 0 else j
            out.append(("x", i, j))
            i = j
            continue
        if code.startswith("/*", i):
            j = code.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(("x", i, j))
            i = j
            continue
        if c in "\"'":
            j = i + 1
            while j < n and code[j] != c and code[j] != "\n":
                j += 2 if code[j] == "\\" else 1
            out.append(("x", i, min(j + 1, n)))
            i = j + 1
            continue
        if c == "`":
            j = _skip_template(code, i + 1)
            out.append(("x", i, j))
            i = j
            continue
        if c == "/" and _regex_allowed(code, out):
            j = i + 1
            in_class = False
            while j < n and code[j] != "\n":
                if code[j] == "\\":
                    j += 2
                    continue
                if code[j] == "[":
                    in_class = True
                elif code[j] == "]":
                    in_class = False
                elif code[j] == "/" and not in_class:
                    break
                j += 1
            j += 1
            while j < n and (code[j].isalnum() or code[j] == "_"):
                j += 1                                   # flags
            out.append(("x", i, min(j, n)))
            i = j
            continue
        m = _IDENT.match(code, i)
        if m:
            out.append(("id", i, m.end()))
            i = m.end()
            continue
        if c.isdigit():
            j = i + 1
            while j < n and (code[j].isalnum() or code[j] in "._"):
                j += 1
            out.append(("num", i, j))
            i = j
            continue
        out.append(("p", i, i + 1))
        i += 1
    return out


def _skip_template(code: str, i: int) -> int:
    """End of a template literal starting after its backtick (handles ${ ... } with nested code)."""
    n = len(code)
    while i < n:
        c = code[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            return i + 1
        if code.startswith("${", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if code[i] in "\"'":
                    q, i = code[i], i + 1
                    while i < n and code[i] != q:
                        i += 2 if code[i] == "\\" else 1
                elif code[i] == "`":
                    i = _skip_template(code, i + 1) - 1
                elif code[i] == "{":
                    depth += 1
                elif code[i] == "}":
                    depth -= 1
                i += 1
            continue
        i += 1
    return n


def _regex_allowed(code: str, toks: List[Tuple[str, int, int]]) -> bool:
    prev = next((t for t in reversed(toks) if t[0] != "x"), None)
    if prev is None:
        return True
    kind, s, e = prev
    if kind == "num":
        return False
    if kind == "id":
        return code[s:e] in _REGEX_AFTER_WORDS
    return code[s:e] not in ")]}"


def guard_loops(code: str) -> str:
    """Adds the guard call at the start of every braced loop body."""
    toks = [t for t in _tokens(code) if t[0] != "x"]
    inserts: List[int] = []
    for k, (kind, s, e) in enumerate(toks):
        if kind != "id":
            continue
        word = code[s:e]
        if k and code[toks[k - 1][1]:toks[k - 1][2]] == ".":
            continue                                       # a property like obj.for
        if word == "do":
            if k + 1 < len(toks) and code[toks[k + 1][1]] == "{":
                inserts.append(toks[k + 1][2])
            continue
        if word not in ("for", "while"):
            continue
        j = k + 1
        if word == "for" and j < len(toks) and code[toks[j][1]:toks[j][2]] == "await":
            j += 1
        if j >= len(toks) or code[toks[j][1]] != "(":
            continue
        depth = 0
        while j < len(toks):
            ch = code[toks[j][1]:toks[j][2]]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j + 1 < len(toks) and code[toks[j + 1][1]] == "{":
            inserts.append(toks[j + 1][2])                 # the do { ... } while (...) tail ends with ";", not "{"
    for pos in sorted(inserts, reverse=True):
        code = code[:pos] + GUARD_CALL + code[pos:]
    return code


_SCRIPT = re.compile(r"(<script\b[^>]*>)(.*?)(</script\s*>)", re.I | re.S)


def guard_html(html: str) -> str:
    """Guards the loops in every inline script of a generated page."""
    def fix(m: re.Match) -> str:
        if re.search(r"\btype\s*=\s*[\"']?(?!text/javascript|module|application/javascript)[\w/+-]+", m.group(1), re.I):
            return m.group(0)                              # JSON or templates: not code
        return m.group(1) + guard_loops(m.group(2)) + m.group(3)
    return _SCRIPT.sub(fix, html)
