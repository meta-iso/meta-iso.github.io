#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CODDY - nowoczesny, w pełni offline edytor kodu (fioletowo-zielono-czarny).

Języki : Python, C++, Java, JavaScript, HTML5
Funkcje: kolorowanie składni, podpowiedzi, analiza błędów na żywo, uruchamianie,
         debugger (pdb / gdb / jdb / node inspect), punkty przerwania, karty,
         znajdź/zamień, komentowanie, zoom, otwieranie istniejących plików.

Uruchomienie : python coddy.py
Budowa .exe  : build_coddy_exe.bat
"""
import ast
import base64
import bisect
import builtins
import codecs
import collections
import keyword
import math
import os
import queue
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
import zlib
from html.parser import HTMLParser
from pathlib import Path

APP = "CODDY"
VERSION = "1.0"
INDENT = "    "

# ======================================================================
#  PALETA
# ======================================================================
C = dict(
    bg="#0b0b10", bg2="#100d19", panel="#171322", line="#2a2140",
    fg="#e6e1f0", dim="#7d7594", purple="#a855f7", purple2="#7c3aed",
    green="#22e58b", green2="#10b981", sel="#3b2a66", err="#ff5370",
    warn="#ffcb6b", cur="#14101e", out="#08080c",
)

TAGSTYLE = {
    "keyword": "#c084fc", "builtin": "#a78bfa", "string": "#4ade80",
    "number": "#f0abfc", "comment": "#6b6385", "function": "#86efac",
    "class": "#34d399", "preproc": "#e879f9", "tag": "#c084fc",
    "attr": "#6ee7b7", "entity": "#f0abfc",
}

# ======================================================================
#  LOGO (czysty Python -> PNG / ICO, bez zewnętrznych bibliotek)
# ======================================================================
def _lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _logo_sample(u, v):
    d = abs(u) ** 5 + abs(v) ** 5
    if d > 1.0:
        return (0.0, 0.0, 0.0, 0.0)
    col = _lerp((28, 16, 52), (6, 6, 10), (u + v + 2) / 4)
    if d > 0.84:
        col = _lerp(col, (168, 85, 247), (d - 0.84) / 0.16)
    r = math.hypot(u, v)
    ang = math.degrees(math.atan2(-v, u))
    if 0.46 <= r <= 0.68 and abs(ang) > 44:
        col = _lerp((168, 85, 247), (34, 229, 139), (u - v + 1.3) / 2.6)
    dist = min(_seg_dist(u, v, -0.10, -0.20, 0.14, 0.0),
               _seg_dist(u, v, -0.10, 0.20, 0.14, 0.0))
    if dist < 0.06:
        col = (34, 229, 139)
    return (col[0], col[1], col[2], 255.0)


def render_logo_rgba(size):
    ss = 3 if size <= 64 else 2
    out = bytearray()
    for y in range(size):
        for x in range(size):
            r = g = b = a = 0.0
            for sy in range(ss):
                for sx in range(ss):
                    u = ((x + (sx + 0.5) / ss) / size) * 2 - 1
                    v = ((y + (sy + 0.5) / ss) / size) * 2 - 1
                    pr, pg, pb, pa = _logo_sample(u, v)
                    r += pr * pa; g += pg * pa; b += pb * pa; a += pa
            if a > 0:
                out += bytes((int(r / a), int(g / a), int(b / a), int(a / (ss * ss))))
            else:
                out += b"\x00\x00\x00\x00"
    return bytes(out)


def png_bytes(w, h, rgba):
    raw = b"".join(b"\x00" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def logo_png(size):
    return png_bytes(size, size, render_logo_rgba(size))


def write_ico(path, size=256):
    png = logo_png(size)
    hdr = struct.pack("<HHH", 0, 1, 1)
    ent = struct.pack("<BBBBHHII", 0 if size >= 256 else size, 0 if size >= 256 else size,
                      0, 0, 1, 32, len(png), 22)
    with open(path, "wb") as f:
        f.write(hdr + ent + png)


# ======================================================================
#  JĘZYKI: słowa kluczowe + kolorowanie składni
# ======================================================================
LANG_ORDER = ["Python", "C++", "Java", "JavaScript", "HTML5"]

_PY_KW = set(keyword.kwlist) | set(getattr(keyword, "softkwlist", []))
_PY_BI = {n for n in dir(builtins) if not n.startswith("_")} | {"self", "cls"}

_CPP_KW = set("""alignas alignof and and_eq asm auto bitand bitor bool break case catch char char8_t char16_t
char32_t class compl concept const consteval constexpr constinit const_cast continue co_await co_return co_yield
decltype default delete do double dynamic_cast else enum explicit export extern false float for friend goto if
inline int long mutable namespace new noexcept not not_eq nullptr operator or or_eq private protected public
register reinterpret_cast requires return short signed sizeof static static_assert static_cast struct switch
template this thread_local throw true try typedef typeid typename union unsigned using virtual void volatile
wchar_t while xor xor_eq override final""".split())
_CPP_BI = set("""std string vector map set unordered_map unordered_set list deque queue stack pair tuple array cout cin
cerr endl printf scanf malloc free size_t unique_ptr shared_ptr make_unique make_shared sort min max swap getline
to_string include define ifdef ifndef endif pragma main FILE NULL""".split())

_JAVA_KW = set("""abstract assert boolean break byte case catch char class const continue default do double else enum
extends final finally float for goto if implements import instanceof int interface long native new package private
protected public return short static strictfp super switch synchronized this throw throws transient try void
volatile while true false null var record sealed permits yield""".split())
_JAVA_BI = set("""String System Math Integer Double Long Boolean Character Object List ArrayList Map HashMap Set HashSet
Arrays Collections Scanner Optional Stream Thread Exception RuntimeException IOException out in err println print
printf main args""".split())

_JS_KW = set("""break case catch class const continue debugger default delete do else export extends finally for
function if import in instanceof let new return super switch this throw try typeof var void while with yield async
await of static get set true false null undefined NaN Infinity from as""".split())
_JS_BI = set("""console document window Math JSON Object Array String Number Boolean Date Promise Map Set Symbol RegExp
Error parseInt parseFloat setTimeout setInterval clearTimeout clearInterval fetch require module exports process
localStorage alert prompt log""".split())

_HTML_TAGS = set("""html head body title meta link script style div span p a img ul ol li table thead tbody tfoot tr td
th form input button label select option textarea h1 h2 h3 h4 h5 h6 header footer nav main section article aside
br hr canvas video audio source iframe svg pre code em strong small b i u blockquote figure figcaption details
summary dialog template""".split())
_HTML_ATTRS = set("""class id href src alt style type name value placeholder rel charset content onclick width height
lang title target action method for checked disabled required readonly min max step data-id""".split())

_BASIC_STR = r"""\"(?:\\.|[^\"\\\n])*\"?|'(?:\\.|[^'\\\n])*'?"""
_NUM = (r"\b0[xX][0-9a-fA-F_]+[uUlL]*\b|\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?[fFlLuUjJ]*\b")


def _compile(parts):
    return re.compile("|".join(parts), re.M)


LANGS = {
    "Python": dict(
        ext=".py", kw=_PY_KW, bi=_PY_BI, comment="#", template=(
            "# Witaj w CODDY!\n\ndef powitanie(imie):\n    print(f\"Czesc, {imie}! Miłego kodowania.\")\n\n\n"
            "if __name__ == \"__main__\":\n    powitanie(\"swiecie\")\n"),
        rx=_compile([
            r"(?P<comment>#[^\n]*)",
            r"(?P<string>(?:[rRbBfFuU]{1,2})?(?:'''[\s\S]*?(?:'''|\Z)|\"\"\"[\s\S]*?(?:\"\"\"|\Z))"
            r"|(?:[rRbBfFuU]{1,2})?(?:" + _BASIC_STR + "))",
            r"(?P<preproc>^[ \t]*@[\w.]+)",
            r"(?P<number>" + _NUM + ")",
            r"(?P<word>[A-Za-z_][A-Za-z0-9_]*)"])),
    "C++": dict(
        ext=".cpp", kw=_CPP_KW, bi=_CPP_BI, comment="//", template=(
            "#include <iostream>\n#include <string>\n\nint main() {\n    std::string imie = \"swiecie\";\n"
            "    std::cout << \"Czesc, \" << imie << \"! CODDY dziala.\" << std::endl;\n    return 0;\n}\n"),
        rx=_compile([
            r"(?P<comment>//[^\n]*|/\*[\s\S]*?(?:\*/|\Z))",
            r"(?P<string>" + _BASIC_STR + ")",
            r"(?P<preproc>^[ \t]*#[ \t]*[A-Za-z_]+(?:[ \t]*<[^>\n]*>)?)",
            r"(?P<number>" + _NUM + ")",
            r"(?P<word>[A-Za-z_][A-Za-z0-9_]*)"])),
    "Java": dict(
        ext=".java", kw=_JAVA_KW, bi=_JAVA_BI, comment="//", template=(
            "public class Main {\n    public static void main(String[] args) {\n"
            "        String imie = \"swiecie\";\n        System.out.println(\"Czesc, \" + imie + \"! CODDY dziala.\");\n"
            "    }\n}\n"),
        rx=_compile([
            r"(?P<comment>//[^\n]*|/\*[\s\S]*?(?:\*/|\Z))",
            r"(?P<string>\"\"\"[\s\S]*?(?:\"\"\"|\Z)|" + _BASIC_STR + ")",
            r"(?P<preproc>^[ \t]*@[\w.]+)",
            r"(?P<number>" + _NUM + ")",
            r"(?P<word>[A-Za-z_$][A-Za-z0-9_$]*)"])),
    "JavaScript": dict(
        ext=".js", kw=_JS_KW, bi=_JS_BI, comment="//", template=(
            "// Witaj w CODDY!\nfunction powitanie(imie) {\n    console.log(`Czesc, ${imie}! CODDY dziala.`);\n}\n\n"
            "powitanie(\"swiecie\");\n"),
        rx=_compile([
            r"(?P<comment>//[^\n]*|/\*[\s\S]*?(?:\*/|\Z))",
            r"(?P<string>`(?:\\[\s\S]|[^`\\])*`?|" + _BASIC_STR
            + r"|(?<=[(,=:\[!&|?{};])[ \t]*/(?![/*])(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\n\[])+/[gimsuyd]*)",
            r"(?P<number>" + _NUM + ")",
            r"(?P<word>[A-Za-z_$][A-Za-z0-9_$]*)"])),
    "HTML5": dict(
        ext=".html", kw=_HTML_TAGS | _HTML_ATTRS, bi=set(), comment="<!--", template=(
            "<!DOCTYPE html>\n<html lang=\"pl\">\n<head>\n    <meta charset=\"UTF-8\">\n"
            "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            "    <title>CODDY</title>\n    <style>\n        body { background:#0b0b10; color:#e6e1f0; font-family:sans-serif; }\n"
            "        h1 { color:#a855f7; }\n        span { color:#22e58b; }\n    </style>\n</head>\n<body>\n"
            "    <h1>Witaj w <span>CODDY</span>!</h1>\n    <p>Edytuj ten plik i otworz go w przegladarce (F5).</p>\n"
            "</body>\n</html>\n"),
        rx=None),
}

EXT2LANG = {".py": "Python", ".pyw": "Python", ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".c": "C++",
            ".h": "C++", ".hpp": "C++", ".java": "Java", ".js": "JavaScript", ".mjs": "JavaScript",
            ".html": "HTML5", ".htm": "HTML5"}

_HTML_TOP = re.compile(r"(?P<comment><!--[\s\S]*?(?:-->|\Z))|(?P<doctype><![A-Za-z][^>]*>?)"
                       r"|(?P<tag></?[A-Za-z][^>]*>?)|(?P<entity>&#?\w+;)")
_HTML_ATTR = re.compile(r"""(?P<name>[^\s=<>/"']+)|(?P<string>"[^"]*"?|'[^']*'?)""")


def tokenize_html(src):
    pos, n = 0, len(src)
    while True:
        m = _HTML_TOP.search(src, pos)
        if not m:
            break
        g = m.lastgroup
        s, e = m.span()
        if g in ("comment", "entity"):
            yield (s, e, g)
            pos = e
        elif g == "doctype":
            yield (s, e, "preproc")
            pos = e
        else:
            text = m.group()
            mt = re.match(r"</?[A-Za-z][\w:-]*", text)
            yield (s, s + mt.end(), "tag")
            rest = text[mt.end():]
            cm = re.search(r"/?>$", rest)
            body_end = cm.start() if cm else len(rest)
            for am in _HTML_ATTR.finditer(rest[:body_end]):
                a_s, a_e = mt.end() + am.start(), mt.end() + am.end()
                if am.lastgroup == "string":
                    yield (s + a_s, s + a_e, "string")
                else:
                    before = rest[:am.start()].rstrip()
                    yield (s + a_s, s + a_e, "string" if before.endswith("=") else "attr")
            if cm:
                yield (s + mt.end() + cm.start(), e, "tag")
            pos = e
            name = mt.group().lstrip("</").lower()
            if name == "script" and not text.startswith("</") and not text.rstrip().endswith("/>"):
                ce = re.compile(r"</script", re.I).search(src, e)
                end_idx = ce.start() if ce else n
                for ts, te, tt in tokenize("JavaScript", src[e:end_idx]):
                    yield (ts + e, te + e, tt)
                pos = end_idx


def tokenize(lang, src):
    """Zwraca (start, koniec, tag) - tagi: keyword, builtin, string, number, comment, function, class, ..."""
    if lang == "HTML5":
        yield from tokenize_html(src)
        return
    L = LANGS[lang]
    kw, bi, n = L["kw"], L["bi"], len(src)
    prev = ""
    for m in L["rx"].finditer(src):
        g = m.lastgroup
        if g != "word":
            yield (m.start(), m.end(), g)
            prev = ""
            continue
        w = m.group()
        s, e = m.span()
        j = e
        while j < n and src[j] in " \t":
            j += 1
        called = src[j:j + 1] == "("
        if w in kw:
            tag = "keyword"
        elif prev in ("def", "function"):
            tag = "function"
        elif prev in ("class", "interface", "enum", "struct", "namespace", "record"):
            tag = "class"
        elif w in bi:
            tag = "builtin"
        elif called:
            tag = "function"
        elif len(w) > 1 and w[0].isupper() and not w.isupper():
            tag = "class"
        else:
            tag = None
        prev = w
        if tag:
            yield (s, e, tag)


# ======================================================================
#  ANALIZA KODU (błędy na żywo)
# ======================================================================
Problem = collections.namedtuple("Problem", "line col sev msg")
_PAIR_CLOSE = {"(": ")", "[": "]", "{": "}"}
_PAIR_OPEN = {")": "(", "]": "[", "}": "{"}


def _line_starts(src):
    starts = [0]
    for m in re.finditer("\n", src):
        starts.append(m.end())
    return starts


def _pos_lc(starts, pos):
    ln = bisect.bisect_right(starts, pos) - 1
    return ln + 1, pos - starts[ln]


def _unterminated(tok):
    q = tok[0]
    if len(tok) < 2 or tok[-1] != q:
        return True
    k, i = 0, len(tok) - 2
    while i > 0 and tok[i] == "\\":
        k += 1
        i -= 1
    return k % 2 == 1


def check_brackets(lang, src):
    probs = []
    starts = _line_starts(src)
    spans = []
    for s, e, t in tokenize(lang, src):
        if t in ("comment", "string", "preproc"):
            spans.append((s, e))
            tx = src[s:e]
            ln, col = _pos_lc(starts, s)
            if t == "comment" and tx.startswith("/*") and (len(tx) < 4 or not tx.endswith("*/")):
                probs.append(Problem(ln, col, "error", "Niezamknięty komentarz /* ... */"))
            elif t == "string" and tx[0] in "\"'" and not tx.startswith('"""'):
                if _unterminated(tx):
                    probs.append(Problem(ln, col, "error", "Niezamknięty ciąg znaków (brak końcowego cudzysłowu)"))
    stack, i, k, n = [], 0, 0, len(src)
    while i < n and len(probs) < 40:
        if k < len(spans) and i >= spans[k][0]:
            i = max(i, spans[k][1])
            k += 1
            continue
        ch = src[i]
        if ch in "([{":
            stack.append((ch, i))
        elif ch in ")]}":
            ln, col = _pos_lc(starts, i)
            if not stack:
                probs.append(Problem(ln, col, "error", f"Nadmiarowy nawias zamykający '{ch}'"))
            else:
                o, _ = stack[-1]
                if _PAIR_OPEN[ch] == o:
                    stack.pop()
                else:
                    probs.append(Problem(ln, col, "error",
                                         f"Niezgodny nawias: oczekiwano '{_PAIR_CLOSE[o]}', jest '{ch}'"))
                    for idx in range(len(stack) - 1, -1, -1):
                        if stack[idx][0] == _PAIR_OPEN[ch]:
                            del stack[idx:]
                            break
        i += 1
    for o, pos in stack[:20]:
        ln, col = _pos_lc(starts, pos)
        probs.append(Problem(ln, col, "error", f"Niezamknięty nawias '{o}' (brakuje '{_PAIR_CLOSE[o]}')"))
    probs.sort(key=lambda p: (p.line, p.col))
    return probs


_PY_SPECIAL = {"__file__", "__name__", "__doc__", "__builtins__", "__spec__", "__loader__", "__package__",
               "__path__", "__debug__", "reveal_type", "WindowsError"}


def analyze_python(src):
    probs = []
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [Problem(e.lineno or 1, max((e.offset or 1) - 1, 0), "error", "Błąd składni: " + str(e.msg))]
    except (ValueError, RecursionError, MemoryError) as e:
        return [Problem(1, 0, "error", "Błąd analizy: " + str(e))]
    try:
        compile(tree, "<coddy>", "exec")
    except SyntaxError as e:
        probs.append(Problem(e.lineno or 1, max((e.offset or 1) - 1, 0), "error", "Błąd składni: " + str(e.msg)))
    except Exception:
        pass

    imported, star = {}, False
    defined = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                nm = a.asname or a.name.split(".")[0]
                imported[nm] = (node.lineno, node.col_offset, a.name)
                defined.add(nm)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            for a in node.names:
                if a.name == "*":
                    star = True
                    continue
                nm = a.asname or a.name
                imported[nm] = (node.lineno, node.col_offset, f"{node.module or '.'}.{a.name}")
                defined.add(nm)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            defined.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                defined.add(node.name)
            if node.type is None:
                probs.append(Problem(node.lineno, node.col_offset, "warning",
                                     "Pusty 'except:' przechwytuje wszystkie wyjątki - podaj typ wyjątku"))
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            defined.update(node.names)
        elif node.__class__.__name__ in ("MatchAs", "MatchStar"):
            if getattr(node, "name", None):
                defined.add(node.name)
        elif node.__class__.__name__ == "MatchMapping":
            if getattr(node, "rest", None):
                defined.add(node.rest)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    for nm, (ln, col, disp) in imported.items():
        if nm not in used:
            probs.append(Problem(ln, col, "warning", f"Nieużywany import: {disp}"))
    if not star:
        seen = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                if n.id not in defined and n.id not in _PY_BI and n.id not in _PY_SPECIAL \
                        and n.id not in dir(builtins) and n.id not in seen:
                    seen.add(n.id)
                    probs.append(Problem(n.lineno, n.col_offset, "warning", f"Niezdefiniowana nazwa: '{n.id}'"))
    probs.sort(key=lambda p: (p.line, p.col))
    return probs[:60]


_HTML_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
              "track", "wbr"}
_HTML_OPTIONAL = {"p", "li", "td", "th", "tr", "thead", "tbody", "tfoot", "option", "dt", "dd", "head", "body",
                  "html", "colgroup", "optgroup"}


class _HtmlChecker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.probs, self.ids = [], [], {}

    def _common(self, tag, attrs):
        ln, col = self.getpos()
        a = dict(attrs)
        if tag == "img" and "alt" not in a:
            self.probs.append(Problem(ln, col, "warning", "Obrazek <img> bez atrybutu alt"))
        if a.get("id"):
            if a["id"] in self.ids:
                self.probs.append(Problem(ln, col, "warning", f"Powtórzony id=\"{a['id']}\" (pierwszy w linii {self.ids[a['id']]})"))
            else:
                self.ids[a["id"]] = ln

    def handle_starttag(self, tag, attrs):
        self._common(tag, attrs)
        if tag not in _HTML_VOID:
            ln, col = self.getpos()
            self.stack.append((tag, ln, col))

    def handle_startendtag(self, tag, attrs):
        self._common(tag, attrs)

    def handle_endtag(self, tag):
        ln, col = self.getpos()
        if tag in _HTML_VOID:
            self.probs.append(Problem(ln, col, "warning", f"Znacznik <{tag}> nie wymaga zamknięcia"))
            return
        idx = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                idx = i
                break
        if idx is None:
            self.probs.append(Problem(ln, col, "error", f"Zbędny znacznik zamykający </{tag}>"))
            return
        popped = self.stack[idx + 1:]
        del self.stack[idx:]
        for t, l, c in popped:
            if t not in _HTML_OPTIONAL:
                self.probs.append(Problem(l, c, "error", f"Niezamknięty znacznik <{t}>"))


def analyze_html(src):
    chk = _HtmlChecker()
    try:
        chk.feed(src)
        chk.close()
    except Exception as e:
        return [Problem(1, 0, "error", f"Błąd analizy HTML: {e}")]
    probs = chk.probs
    for t, l, c in chk.stack:
        if t not in _HTML_OPTIONAL:
            probs.append(Problem(l, c, "error", f"Niezamknięty znacznik <{t}>"))
    if not re.match(r"\s*<!doctype html", src, re.I):
        probs.append(Problem(1, 0, "warning", "Brak deklaracji <!DOCTYPE html> na początku pliku"))
    probs.sort(key=lambda p: (p.line, p.col))
    return probs[:60]


def analyze(lang, src):
    if not src.strip() or len(src) > 400_000:
        return []
    try:
        if lang == "Python":
            return analyze_python(src)
        if lang == "HTML5":
            return analyze_html(src)
        return check_brackets(lang, src)
    except Exception:
        return []


# ---- głęboka analiza przez kompilatory (jeśli są zainstalowane) -------------
_GCC_RX = re.compile(r"^(?:.*[\\/])?([^\\/:\s][^\\/:]*?):(\d+):(?:(\d+):)?\s*(fatal error|error|warning):\s*(.*)$")


def java_main_class(src, fallback="Main"):
    m = re.search(r"\bpublic\s+(?:final\s+|abstract\s+)*(?:class|interface|enum|record)\s+(\w+)", src)
    if m:
        return m.group(1)
    classes = [(m.start(), m.group(1)) for m in re.finditer(r"\bclass\s+(\w+)", src)]
    if not classes:
        return fallback
    mi = src.find("void main")
    if mi >= 0:
        before = [c for c in classes if c[0] < mi]
        if before:
            return before[-1][1]
    return classes[0][1]


def _parse_gcc_like(output, fname):
    probs = []
    for line in output.splitlines():
        m = _GCC_RX.match(line.strip())
        if m and m.group(1) == fname:
            sev = "warning" if m.group(4) == "warning" else "error"
            probs.append(Problem(int(m.group(2)), int(m.group(3) or 1) - 1, sev, m.group(5)))
    return probs


def deep_check(lang, src):
    """Zwraca (lista_problemów, notatka). Notatka != None gdy narzędzie niedostępne."""
    tmp = tempfile.mkdtemp(prefix="coddy_chk_")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        def run(cmd):
            return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=40, cwd=tmp, creationflags=flags)
        if lang == "C++":
            exe = shutil.which("g++")
            if not exe:
                return [], "Brak g++ w PATH - działa tylko podstawowa analiza (zainstaluj MinGW-w64/MSYS2)."
            fp = os.path.join(tmp, "main.cpp")
            with open(fp, "w", encoding="utf-8") as f:
                f.write(src)
            r = run([exe, "-fsyntax-only", "-Wall", "-Wextra", "-std=c++17", fp])
            return _parse_gcc_like(r.stdout + "\n" + r.stderr, "main.cpp"), None
        if lang == "Java":
            exe = shutil.which("javac")
            if not exe:
                return [], "Brak javac w PATH - działa tylko podstawowa analiza (zainstaluj JDK)."
            cls = java_main_class(src)
            fp = os.path.join(tmp, cls + ".java")
            with open(fp, "w", encoding="utf-8") as f:
                f.write(src)
            r = run([exe, "-Xlint:all", "-encoding", "UTF-8", "-d", tmp, fp])
            return _parse_gcc_like(r.stdout + "\n" + r.stderr, cls + ".java"), None
        if lang == "JavaScript":
            exe = shutil.which("node")
            if not exe:
                return [], "Brak Node.js w PATH - działa tylko podstawowa analiza."
            fp = os.path.join(tmp, "main.js")
            with open(fp, "w", encoding="utf-8") as f:
                f.write(src)
            r = run([exe, "--check", fp])
            txt = r.stderr + "\n" + r.stdout
            lm = re.search(r"^.*main\.js:(\d+)\s*$", txt, re.M)
            em = re.search(r"^(\w*Error: .*)$", txt, re.M)
            if r.returncode != 0 and lm and em:
                return [Problem(int(lm.group(1)), 0, "error", em.group(1))], None
            return [], None
        return [], None
    except subprocess.TimeoutExpired:
        return [], "Analiza kompilatorem przekroczyła limit czasu."
    except Exception as e:
        return [], f"Analiza kompilatorem nieudana: {e}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ======================================================================
#  NARZĘDZIA POMOCNICZE
# ======================================================================
def find_python():
    if not getattr(sys, "frozen", False):
        return sys.executable
    for name in ("python", "py", "python3"):
        p = shutil.which(name)
        if p:
            return p
    return None


def child_env():
    env = os.environ.copy()
    for k in list(env):
        if k in ("PYTHONHOME", "PYTHONPATH", "_MEIPASS2") or k.startswith("_PYI"):
            env.pop(k, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def open_terminal(args, cwd):
    """Otwiera interaktywną konsolę z podanym poleceniem (używane przez debugger)."""
    if os.name == "nt":
        subprocess.Popen(args, cwd=cwd, creationflags=subprocess.CREATE_NEW_CONSOLE, env=child_env())
        return True
    if sys.platform == "darwin":
        cmd = "cd " + shlex.quote(cwd) + "; " + " ".join(shlex.quote(a) for a in args)
        cmd = cmd.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{cmd}"'])
        return True
    for term in (("x-terminal-emulator", "-e"), ("gnome-terminal", "--"), ("konsole", "-e"),
                 ("xfce4-terminal", "-x"), ("xterm", "-e")):
        if shutil.which(term[0]):
            subprocess.Popen(list(term) + list(args), cwd=cwd, env=child_env())
            return True
    return False


def read_text_file(path):
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            return raw.decode(enc).replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


TOOL_HINTS = {
    "python": "Zainstaluj Pythona (python.org) i dodaj go do PATH.",
    "g++": "Zainstaluj MinGW-w64 / MSYS2 (g++ i gdb) i dodaj do PATH.",
    "gcc": "Zainstaluj MinGW-w64 / MSYS2 (gcc i gdb) i dodaj do PATH.",
    "gdb": "Zainstaluj gdb (MinGW-w64 / MSYS2) i dodaj do PATH.",
    "javac": "Zainstaluj JDK (np. Temurin) i dodaj do PATH.",
    "java": "Zainstaluj JDK (np. Temurin) i dodaj do PATH.",
    "jdb": "Zainstaluj JDK (jdb jest jego częścią) i dodaj do PATH.",
    "node": "Zainstaluj Node.js (nodejs.org) i dodaj do PATH.",
}

# ======================================================================
#  GUI
# ======================================================================
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinter import font as tkfont


def pick_font_family():
    try:
        fams = set(tkfont.families())
    except Exception:
        fams = set()
    for f in ("JetBrains Mono", "Cascadia Code", "Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Menlo",
              "Liberation Mono", "Courier New"):
        if f in fams:
            return f
    return "TkFixedFont"


class Doc:
    """Pojedyncza karta edytora."""

    def __init__(self, app, path, lang, content):
        self.app, self.path, self.lang = app, path, lang
        self.dirty = False
        self.breakpoints = set()
        self.problems = []
        self.deep_problems = []
        self._loading = True
        self._jobs = {}
        self.untitled_name = None
        self.pristine_template = None

        self.frame = tk.Frame(app.nb, bg=C["bg"])
        self.frame.rowconfigure(0, weight=1)
        self.frame.columnconfigure(1, weight=1)
        self.gutter = tk.Canvas(self.frame, width=62, bg=C["bg2"], highlightthickness=0, bd=0, cursor="arrow")
        self.text = tk.Text(self.frame, wrap="none", undo=True, maxundo=-1, font=app.font, bg=C["bg"], fg=C["fg"],
                            insertbackground=C["green"], insertwidth=2, selectbackground=C["sel"],
                            selectforeground="#ffffff", inactiveselectbackground=C["sel"], relief="flat", bd=0,
                            padx=8, pady=4, highlightthickness=0, spacing1=1, spacing3=1)
        self.vsb = ttk.Scrollbar(self.frame, orient="vertical", command=self.text.yview)
        self.hsb = ttk.Scrollbar(self.frame, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=self._yscroll, xscrollcommand=self.hsb.set)
        self.gutter.grid(row=0, column=0, sticky="ns")
        self.text.grid(row=0, column=1, sticky="nsew")
        self.vsb.grid(row=0, column=2, sticky="ns")
        self.hsb.grid(row=1, column=0, columnspan=2, sticky="ew")

        t = self.text
        t.tag_configure("curline", background=C["cur"])
        t.tag_configure("p_warn", background="#231d0f")
        t.tag_configure("p_err", background="#2a1020")
        for tag, col in TAGSTYLE.items():
            t.tag_configure(tag, foreground=col)
        t.tag_configure("found", background=C["purple2"], foreground="#ffffff")
        try:
            t.tag_configure("p_err", underline=True, underlinefg=C["err"])
            t.tag_configure("p_warn", underline=True, underlinefg=C["warn"])
        except tk.TclError:
            pass
        t.tag_raise("sel")
        self.apply_tabs()

        t.bind("<<Modified>>", self._on_modified)
        t.bind("<Key>", self.on_key)
        t.bind("<KeyRelease>", self.on_keyrelease)
        t.bind("<ButtonRelease-1>", lambda e: (self.ac_hide(), self.after_cursor()))
        t.bind("<Button-1>", lambda e: self.ac_hide())
        t.bind("<Return>", self.on_return)
        t.bind("<Tab>", self.on_tab)
        t.bind("<Shift-Tab>", self.on_shift_tab)
        t.bind("<ISO_Left_Tab>", self.on_shift_tab)
        t.bind("<Up>", lambda e: self.ac_move(-1))
        t.bind("<Down>", lambda e: self.ac_move(1))
        t.bind("<Escape>", lambda e: self.ac_escape())
        t.bind("<Control-space>", lambda e: (self.ac_show(force=True), "break")[1])
        t.bind("<Control-y>", lambda e: (self._redo(), "break")[1])
        t.bind("<MouseWheel>", self._wheel)
        t.bind("<Button-4>", self._wheel)
        t.bind("<Button-5>", self._wheel)
        t.bind("<Configure>", lambda e: self.draw_gutter())
        self.gutter.bind("<Button-1>", self._gutter_click)
        self.gutter.bind("<MouseWheel>", lambda e: self.text.event_generate("<MouseWheel>", delta=e.delta))
        app.bind_shortcuts(t)

        self.popup = None
        self.listbox = None
        self.set_content(content)

    # ---- ogólne ---------------------------------------------------------
    def apply_tabs(self):
        self.text.configure(tabs=(self.app.font.measure(" " * 4),))

    def _redo(self):
        try:
            self.text.edit_redo()
        except tk.TclError:
            pass

    def _wheel(self, e):
        if e.state & 0x4:  # Ctrl + kółko = zoom
            up = (getattr(e, "delta", 0) > 0) or e.num == 4
            self.app.zoom(1 if up else -1)
            return "break"
        return None

    def src(self):
        return self.text.get("1.0", "end-1c")

    def set_content(self, content):
        self._loading = True
        t = self.text
        t.delete("1.0", "end")
        t.insert("1.0", content)
        t.edit_reset()
        t.edit_modified(False)
        t.mark_set("insert", "1.0")
        self._loading = False
        self.rehighlight()
        self.run_quick()
        self.after_cursor()

    def set_lang(self, lang):
        self.lang = lang
        self.rehighlight()
        self.run_quick()

    def goto(self, line, col=0):
        t = self.text
        last = int(t.index("end-1c").split(".")[0])
        line = max(1, min(line, last))
        t.mark_set("insert", f"{line}.{col}")
        t.see(f"{line}.0")
        t.focus_set()
        self.after_cursor()

    # ---- zdarzenia zmian ---------------------------------------------------
    def _on_modified(self, e=None):
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        if self._loading:
            return
        if not self.dirty:
            self.dirty = True
            self.app.refresh_tab(self)
        self.deep_problems = []
        self._schedule("hl", 140, self.rehighlight)
        self._schedule("an", 650, self.run_quick)
        self.text.after_idle(self.draw_gutter)

    def _schedule(self, key, ms, fn):
        old = self._jobs.get(key)
        if old:
            try:
                self.text.after_cancel(old)
            except Exception:
                pass
        self._jobs[key] = self.text.after(ms, fn)

    def _yscroll(self, a, b):
        self.vsb.set(a, b)
        self.draw_gutter()

    # ---- kolorowanie ---------------------------------------------------------
    def rehighlight(self):
        t = self.text
        src = self.src()
        for tag in TAGSTYLE:
            t.tag_remove(tag, "1.0", "end")
        if len(src) > 400_000:
            return
        starts = _line_starts(src)
        ranges = collections.defaultdict(list)
        try:
            for s, e, tag in tokenize(self.lang, src):
                if tag not in TAGSTYLE:
                    continue
                l1, c1 = _pos_lc(starts, s)
                l2, c2 = _pos_lc(starts, e)
                ranges[tag] += [f"{l1}.{c1}", f"{l2}.{c2}"]
        except Exception:
            return
        for tag, idxs in ranges.items():
            for i in range(0, len(idxs), 400):
                t.tag_add(tag, *idxs[i:i + 400])

    # ---- analiza ------------------------------------------------------------
    def run_quick(self):
        self.problems = analyze(self.lang, self.src())
        self.apply_problems()

    def all_problems(self):
        seen, out = set(), []
        for p in self.problems + self.deep_problems:
            k = (p.line, p.msg)
            if k not in seen:
                seen.add(k)
                out.append(p)
        out.sort(key=lambda p: (p.line, p.col))
        return out

    def apply_problems(self):
        t = self.text
        t.tag_remove("p_err", "1.0", "end")
        t.tag_remove("p_warn", "1.0", "end")
        last = int(t.index("end-1c").split(".")[0])
        for p in self.all_problems():
            if p.line <= last:
                t.tag_add("p_err" if p.sev == "error" else "p_warn", f"{p.line}.0", f"{p.line}.end")
        self.draw_gutter()
        if self.app.current() is self:
            self.app.show_problems(self)

    # ---- marginesy ---------------------------------------------------------
    def draw_gutter(self):
        g, t = self.gutter, self.text
        g.delete("all")
        cur = int(t.index("insert").split(".")[0])
        perr = {}
        for p in self.all_problems():
            if perr.get(p.line) != "error":
                perr[p.line] = p.sev
        i = t.index("@0,0")
        prev = -1
        while True:
            d = t.dlineinfo(i)
            if d is None:
                break
            ln = int(i.split(".")[0])
            if ln == prev:
                break
            prev = ln
            y, h = d[1], d[3]
            g.create_text(46, y + h / 2, text=str(ln), anchor="e", font=self.app.gfont,
                          fill=C["green"] if ln == cur else C["dim"])
            if ln in self.breakpoints:
                g.create_oval(8, y + h / 2 - 5, 18, y + h / 2 + 5, fill=C["err"], outline="")
            if ln in perr:
                col = C["err"] if perr[ln] == "error" else C["warn"]
                g.create_rectangle(56, y + 2, 60, y + h - 2, fill=col, outline="")
            i = t.index(f"{i}+1line")
            if int(i.split(".")[0]) == ln:
                break

    def _gutter_click(self, e):
        ln = int(self.text.index(f"@0,{e.y}").split(".")[0])
        if e.x < 28:
            if ln in self.breakpoints:
                self.breakpoints.discard(ln)
            else:
                self.breakpoints.add(ln)
            self.draw_gutter()
        else:
            self.goto(ln)

    def after_cursor(self, e=None):
        t = self.text
        t.tag_remove("curline", "1.0", "end")
        ln = t.index("insert").split(".")[0]
        t.tag_add("curline", f"{ln}.0", f"{ln}.0 lineend+1c")
        self.app.update_status(self)
        self.draw_gutter()

    # ---- klawisze ---------------------------------------------------------
    def on_key(self, e):
        ch = e.char
        if not ch or len(ch) != 1 or (e.state & 0x4) or ord(ch) < 32:
            return None
        t = self.text
        nxt = t.get("insert", "insert+1c")
        has_sel = bool(t.tag_ranges("sel"))
        if ch in ")]}" and nxt == ch:
            t.mark_set("insert", "insert+1c")
            return "break"
        if ch in "([{":
            close = _PAIR_CLOSE[ch]
            if has_sel:
                s = t.get("sel.first", "sel.last")
                t.delete("sel.first", "sel.last")
                t.insert("insert", ch + s + close)
            else:
                t.insert("insert", ch + close)
                t.mark_set("insert", "insert-1c")
            return "break"
        if ch in "\"'":
            if self.lang == "HTML5" and not (ch == '"' and t.get("insert-1c", "insert") == "="):
                return None
            if has_sel:
                s = t.get("sel.first", "sel.last")
                t.delete("sel.first", "sel.last")
                t.insert("insert", ch + s + ch)
                return "break"
            if nxt == ch:
                t.mark_set("insert", "insert+1c")
                return "break"
            prev = t.get("insert-1c", "insert") if t.compare("insert", "!=", "1.0") else ""
            if prev.isalnum() or prev == "\\" or prev == ch:
                return None
            t.insert("insert", ch + ch)
            t.mark_set("insert", "insert-1c")
            return "break"
        return None

    def on_keyrelease(self, e):
        ks = e.keysym
        if ks in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Up", "Down", "Return",
                  "Tab", "Escape", "Caps_Lock", "ISO_Left_Tab"):
            self.after_cursor()
            return
        if (len(ks) == 1 and (ks.isalnum() or ks == "_")) or (ks == "BackSpace" and self.popup):
            self.ac_show()
        else:
            self.ac_hide()
        self.after_cursor()

    def on_return(self, e):
        if self.popup:
            self.ac_accept()
            return "break"
        t = self.text
        if t.tag_ranges("sel"):
            t.delete("sel.first", "sel.last")
        line = t.get("insert linestart", "insert")
        indent = re.match(r"[ \t]*", line).group()
        before = line.rstrip()
        after = t.get("insert", "insert lineend")
        extra = ""
        if self.lang == "Python":
            if before.endswith(":") or before.endswith(("(", "[", "{")):
                extra = INDENT
        elif self.lang == "HTML5":
            m = re.search(r"<([A-Za-z][\w-]*)(?:\s[^<>]*)?>$", before)
            if m and m.group(1).lower() not in _HTML_VOID and not before.endswith("/>"):
                extra = INDENT
        elif before.endswith(("{", "(", "[")):
            extra = INDENT
        if extra and after.lstrip().startswith(("}", ")", "]", "</")):
            t.insert("insert", "\n" + indent + extra + "\n" + indent)
            t.mark_set("insert", f"insert-{len(indent) + 1}c")
        else:
            t.insert("insert", "\n" + indent + extra)
        t.see("insert")
        self.after_cursor()
        return "break"

    def _sel_lines(self):
        t = self.text
        if t.tag_ranges("sel"):
            a = int(t.index("sel.first").split(".")[0])
            bi = t.index("sel.last")
            b = int(bi.split(".")[0])
            if bi.endswith(".0") and b > a:
                b -= 1
            return a, b
        n = int(t.index("insert").split(".")[0])
        return n, n

    def on_tab(self, e):
        if self.popup:
            self.ac_accept()
            return "break"
        t = self.text
        if t.tag_ranges("sel"):
            a, b = self._sel_lines()
            for ln in range(a, b + 1):
                t.insert(f"{ln}.0", INDENT)
            t.tag_remove("sel", "1.0", "end")
            t.tag_add("sel", f"{a}.0", f"{b}.end")
            return "break"
        t.insert("insert", INDENT)
        return "break"

    def on_shift_tab(self, e):
        t = self.text
        a, b = self._sel_lines()
        for ln in range(a, b + 1):
            line = t.get(f"{ln}.0", f"{ln}.end")
            if line.startswith("\t"):
                t.delete(f"{ln}.0", f"{ln}.1")
            else:
                k = len(line) - len(line.lstrip(" "))
                t.delete(f"{ln}.0", f"{ln}.{min(k, 4)}")
        return "break"

    def toggle_comment(self):
        t = self.text
        pre = LANGS[self.lang]["comment"]
        suf = ""
        if self.lang == "HTML5":
            pre, suf = "<!-- ", " -->"
        else:
            pre = pre + " "
        a, b = self._sel_lines()
        lines = [(ln, t.get(f"{ln}.0", f"{ln}.end")) for ln in range(a, b + 1)]
        body = [(ln, s) for ln, s in lines if s.strip()]
        if not body:
            return
        t.edit_separator()
        if all(s.lstrip().startswith(pre.strip()) for _, s in body):
            for ln, s in body:
                k = s.index(pre.strip())
                end = k + len(pre.strip())
                if s[end:end + 1] == " ":
                    end += 1
                t.delete(f"{ln}.{k}", f"{ln}.{end}")
                if suf:
                    cur = t.get(f"{ln}.0", f"{ln}.end")
                    if cur.rstrip().endswith(suf.strip()):
                        k2 = cur.rstrip().rfind(suf.strip())
                        t.delete(f"{ln}.{k2 - (1 if cur[k2 - 1:k2] == ' ' else 0)}", f"{ln}.end")
        else:
            ind = min(len(s) - len(s.lstrip()) for _, s in body)
            for ln, s in body:
                if suf:
                    t.insert(f"{ln}.end", suf)
                t.insert(f"{ln}.{ind}", pre)
        t.edit_separator()

    # ---- autouzupełnianie ----------------------------------------------------
    def cur_prefix(self):
        line = self.text.get("insert linestart", "insert")
        m = re.search(r"[A-Za-z_$][A-Za-z0-9_$]*$", line)
        return m.group() if m else ""

    def ac_candidates(self, prefix):
        L = LANGS[self.lang]
        pool = set(L["kw"]) | set(L["bi"])
        src = self.src()
        if len(src) < 300_000:
            pool |= set(re.findall(r"[A-Za-z_$][A-Za-z0-9_$]{2,}", src))
        pl = prefix.lower()
        c = [w for w in pool if w.lower().startswith(pl) and w != prefix]
        c.sort(key=lambda w: (not w.startswith(prefix), len(w), w.lower()))
        return c[:10]

    def ac_show(self, force=False):
        prefix = self.cur_prefix()
        if not prefix or (len(prefix) < 2 and not force):
            self.ac_hide()
            return
        cands = self.ac_candidates(prefix)
        if not cands:
            self.ac_hide()
            return
        bb = self.text.bbox("insert")
        if not bb:
            self.ac_hide()
            return
        if not self.popup:
            self.popup = tk.Toplevel(self.text)
            self.popup.wm_overrideredirect(True)
            try:
                self.popup.attributes("-topmost", True)
            except tk.TclError:
                pass
            self.listbox = tk.Listbox(self.popup, bg=C["panel"], fg=C["fg"], selectbackground=C["purple2"],
                                      selectforeground="#ffffff", activestyle="none", bd=0, highlightthickness=1,
                                      highlightbackground=C["purple"], font=self.app.font, exportselection=False)
            self.listbox.pack()
            self.listbox.bind("<ButtonRelease-1>", lambda e: self.ac_accept())
        self.listbox.delete(0, "end")
        for w in cands:
            self.listbox.insert("end", w)
        self.listbox.configure(height=len(cands), width=max(14, max(len(w) for w in cands) + 2))
        self.listbox.selection_set(0)
        self.listbox.activate(0)
        x = self.text.winfo_rootx() + bb[0]
        y = self.text.winfo_rooty() + bb[1] + bb[3] + 2
        self.popup.geometry(f"+{x}+{y}")

    def ac_hide(self):
        if self.popup:
            try:
                self.popup.destroy()
            except Exception:
                pass
            self.popup = None
            self.listbox = None

    def ac_escape(self):
        if self.popup:
            self.ac_hide()
            return "break"
        return None

    def ac_move(self, d):
        if not self.popup:
            return None
        lb = self.listbox
        cur = lb.curselection()
        i = (cur[0] if cur else 0) + d
        i = max(0, min(lb.size() - 1, i))
        lb.selection_clear(0, "end")
        lb.selection_set(i)
        lb.activate(i)
        lb.see(i)
        return "break"

    def ac_accept(self):
        if not self.popup:
            return
        sel = self.listbox.curselection()
        if not sel:
            self.ac_hide()
            return
        word = self.listbox.get(sel[0])
        prefix = self.cur_prefix()
        self.ac_hide()
        if prefix:
            self.text.delete(f"insert-{len(prefix)}c", "insert")
        self.text.insert("insert", word)


class App:
    def __init__(self, root, files=None):
        self.root = root
        root.title(APP)
        root.geometry("1280x800")
        root.minsize(760, 480)
        root.configure(bg=C["bg"])
        self.docs = {}
        self.untitled_n = 0
        self.last_dir = os.path.expanduser("~")
        self.proc = None
        self.running = False
        self.q = queue.Queue()
        self.path_map = {}
        self.link_n = 0
        self.font = tkfont.Font(family=pick_font_family(), size=12)
        self.gfont = tkfont.Font(family=self.font.cget("family"), size=10)
        self.lang_var = tk.StringVar(value="Python")
        self.tools = []

        self.icon_img = tk.PhotoImage(data=base64.b64encode(logo_png(64)))
        self.logo_small = tk.PhotoImage(data=base64.b64encode(logo_png(30)))
        try:
            root.iconphoto(True, self.icon_img)
        except tk.TclError:
            pass

        self._style()
        self._build_menubar()
        self._build_toolbar()
        self._build_statusbar()
        self._build_body()
        self.bind_shortcuts(root, is_root=True)
        root.protocol("WM_DELETE_WINDOW", self.on_exit)

        opened = False
        for f in files or []:
            if os.path.isfile(f):
                self.open_path(f)
                opened = True
        if not opened:
            self.new_doc("Python")
        self._poll()

    # ---- wygląd ttk ---------------------------------------------------------
    def _style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("TNotebook", background=C["bg"], borderwidth=0, tabmargins=(0, 0, 0, 0))
        st.configure("TNotebook.Tab", background=C["panel"], foreground=C["dim"], padding=(16, 7), borderwidth=0)
        st.map("TNotebook.Tab", background=[("selected", C["bg"]), ("active", C["line"])],
               foreground=[("selected", C["green"]), ("active", C["fg"])])
        for o in ("Vertical", "Horizontal"):
            st.configure(f"{o}.TScrollbar", background=C["line"], troughcolor=C["bg"], bordercolor=C["bg"],
                         arrowcolor=C["purple"], lightcolor=C["line"], darkcolor=C["line"], relief="flat")
            st.map(f"{o}.TScrollbar", background=[("active", C["purple2"])])
        st.configure("Treeview", background=C["panel"], fieldbackground=C["panel"], foreground=C["fg"],
                     borderwidth=0, rowheight=24)
        st.configure("Treeview.Heading", background=C["line"], foreground=C["purple"], relief="flat")
        st.map("Treeview", background=[("selected", C["sel"])], foreground=[("selected", "#ffffff")])

    def _menu(self, parent):
        return tk.Menu(parent, tearoff=0, bg=C["panel"], fg=C["fg"], activebackground=C["purple2"],
                       activeforeground="#ffffff", bd=0, relief="flat")

    def _build_menubar(self):
        bar = tk.Frame(self.root, bg=C["bg2"])
        bar.pack(fill="x")
        self.menubar = bar

        def add(title):
            mb = tk.Menubutton(bar, text=title, bg=C["bg2"], fg=C["fg"], activebackground=C["sel"],
                               activeforeground=C["green"], bd=0, padx=11, pady=5, relief="flat")
            m = self._menu(mb)
            mb["menu"] = m
            mb.pack(side="left")
            return m

        m = add("Plik")
        m.add_command(label="Nowy plik", accelerator="Ctrl+N", command=lambda: self.new_doc(self.lang_var.get()))
        m.add_command(label="Otwórz…", accelerator="Ctrl+O", command=self.open_dialog)
        m.add_separator()
        m.add_command(label="Zapisz", accelerator="Ctrl+S", command=self.save)
        m.add_command(label="Zapisz jako…", accelerator="Ctrl+Shift+S", command=self.save_as)
        m.add_separator()
        m.add_command(label="Zamknij kartę", accelerator="Ctrl+W", command=self.close_current)
        m.add_command(label="Wyjście", command=self.on_exit)

        m = add("Edycja")
        m.add_command(label="Cofnij", accelerator="Ctrl+Z", command=lambda: self._cur_text_event("<<Undo>>"))
        m.add_command(label="Ponów", accelerator="Ctrl+Y", command=lambda: self._cur_text_event("<<Redo>>"))
        m.add_separator()
        m.add_command(label="Wytnij", accelerator="Ctrl+X", command=lambda: self._cur_text_event("<<Cut>>"))
        m.add_command(label="Kopiuj", accelerator="Ctrl+C", command=lambda: self._cur_text_event("<<Copy>>"))
        m.add_command(label="Wklej", accelerator="Ctrl+V", command=lambda: self._cur_text_event("<<Paste>>"))
        m.add_command(label="Zaznacz wszystko", accelerator="Ctrl+A", command=self.select_all)
        m.add_separator()
        m.add_command(label="Znajdź / Zamień…", accelerator="Ctrl+F", command=self.find_dialog)
        m.add_command(label="Idź do linii…", accelerator="Ctrl+G", command=self.goto_dialog)
        m.add_command(label="Przełącz komentarz", accelerator="Ctrl+/", command=self.toggle_comment)
        m.add_command(label="Podpowiedzi", accelerator="Ctrl+Spacja", command=self.force_complete)

        m = add("Język")
        for i, lg in enumerate(LANG_ORDER):
            m.add_radiobutton(label=lg, variable=self.lang_var, value=lg, accelerator=f"Alt+{i + 1}",
                              command=self.on_lang_change)

        m = add("Uruchom")
        m.add_command(label="Uruchom kod", accelerator="F5", command=self.run_current)
        m.add_command(label="Debuguj", accelerator="F6", command=self.debug_current)
        m.add_command(label="Analizuj kod (kompilator)", accelerator="F7", command=self.deep_analyze)
        m.add_command(label="Zatrzymaj", accelerator="Shift+F5", command=self.stop)
        m.add_separator()
        m.add_command(label="Przełącz punkt przerwania", accelerator="F9", command=self.toggle_breakpoint)

        m = add("Widok")
        m.add_command(label="Powiększ", accelerator="Ctrl++", command=lambda: self.zoom(1))
        m.add_command(label="Pomniejsz", accelerator="Ctrl+-", command=lambda: self.zoom(-1))
        m.add_command(label="Domyślny rozmiar", accelerator="Ctrl+0", command=lambda: self.zoom(0))
        m.add_separator()
        m.add_command(label="Wyczyść wyjście", command=self.clear_out)

        m = add("Pomoc")
        m.add_command(label="Skróty klawiszowe", command=self.show_help)
        m.add_command(label="O programie CODDY", command=self.show_about)

    def _build_toolbar(self):
        tb = tk.Frame(self.root, bg=C["bg"], height=46)
        tb.pack(fill="x")
        tk.Label(tb, image=self.logo_small, bg=C["bg"]).pack(side="left", padx=(10, 6), pady=6)
        tk.Label(tb, text="COD", bg=C["bg"], fg=C["purple"], font=("Segoe UI", 15, "bold")).pack(side="left")
        tk.Label(tb, text="DY", bg=C["bg"], fg=C["green"], font=("Segoe UI", 15, "bold")).pack(side="left", padx=(0, 16))

        def btn(text, cmd, fg, hover):
            b = tk.Button(tb, text=text, command=cmd, bg=C["panel"], fg=fg, activebackground=hover,
                          activeforeground="#ffffff", bd=0, padx=13, pady=5, relief="flat", cursor="hand2",
                          font=("Segoe UI", 10, "bold"))
            b.bind("<Enter>", lambda e: b.configure(bg=C["line"]))
            b.bind("<Leave>", lambda e: b.configure(bg=C["panel"]))
            b.pack(side="left", padx=3, pady=7)
            return b
        btn("▶ Uruchom", self.run_current, C["green"], C["green2"])
        btn("◉ Debuguj", self.debug_current, C["purple"], C["purple2"])
        btn("✔ Analizuj", self.deep_analyze, C["fg"], C["purple2"])
        self.stop_btn = btn("■ Stop", self.stop, C["err"], C["err"])

        self.lang_mb = tk.Menubutton(tb, textvariable=self.lang_var, bg=C["panel"], fg=C["green"],
                                     activebackground=C["line"], activeforeground=C["green"], bd=0, padx=14,
                                     pady=5, relief="flat", font=("Segoe UI", 10, "bold"), indicatoron=True)
        lm = self._menu(self.lang_mb)
        for lg in LANG_ORDER:
            lm.add_radiobutton(label=lg, variable=self.lang_var, value=lg, command=self.on_lang_change)
        self.lang_mb["menu"] = lm
        self.lang_mb.pack(side="right", padx=12, pady=7)
        tk.Label(tb, text="Język:", bg=C["bg"], fg=C["dim"], font=("Segoe UI", 10)).pack(side="right")
        tk.Frame(self.root, bg=C["purple2"], height=1).pack(fill="x")

    def _build_body(self):
        self.paned = tk.PanedWindow(self.root, orient="vertical", sashwidth=5, bg=C["line"], bd=0,
                                    sashrelief="flat", opaqueresize=True)
        self.paned.pack(fill="both", expand=True)
        self.nb = ttk.Notebook(self.paned)
        self.nb.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.nb.bind("<Button-2>", self._middle_close)
        self.paned.add(self.nb, minsize=160, stretch="always")

        bottom = tk.Frame(self.paned, bg=C["bg"])
        self.bnb = ttk.Notebook(bottom)
        self.bnb.pack(fill="both", expand=True)
        self.paned.add(bottom, minsize=80, height=210, stretch="never")

        of = tk.Frame(self.bnb, bg=C["out"])
        of.rowconfigure(0, weight=1)
        of.columnconfigure(0, weight=1)
        self.output = tk.Text(of, bg=C["out"], fg=C["fg"], font=self.font, bd=0, relief="flat", wrap="word",
                              highlightthickness=0, padx=8, pady=4, state="disabled", insertbackground=C["green"],
                              selectbackground=C["sel"])
        osb = ttk.Scrollbar(of, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=osb.set)
        self.output.grid(row=0, column=0, sticky="nsew")
        osb.grid(row=0, column=1, sticky="ns")
        for tag, col in (("err", C["err"]), ("warn", C["warn"]), ("ok", C["green"]), ("info", C["purple"]),
                         ("stdin", "#f0abfc")):
            self.output.tag_configure(tag, foreground=col)
        row = tk.Frame(of, bg=C["panel"])
        row.grid(row=1, column=0, columnspan=2, sticky="ew")
        tk.Label(row, text=" stdin ›", bg=C["panel"], fg=C["green"], font=self.font).pack(side="left")
        self.stdin = tk.Entry(row, bg=C["panel"], fg=C["fg"], insertbackground=C["green"], bd=0, relief="flat",
                              font=self.font, highlightthickness=0)
        self.stdin.pack(side="left", fill="x", expand=True, padx=6, pady=5)
        self.stdin.bind("<Return>", self.send_stdin)
        tk.Button(row, text="Wyczyść", command=self.clear_out, bg=C["panel"], fg=C["dim"], bd=0, relief="flat",
                  activebackground=C["line"], activeforeground=C["fg"], cursor="hand2").pack(side="right", padx=6)
        self.bnb.add(of, text="  WYJŚCIE  ")

        pf = tk.Frame(self.bnb, bg=C["panel"])
        pf.rowconfigure(0, weight=1)
        pf.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(pf, columns=("sev", "line", "msg"), show="headings", selectmode="browse")
        self.tree.heading("sev", text="")
        self.tree.heading("line", text="Linia")
        self.tree.heading("msg", text="Opis")
        self.tree.column("sev", width=34, stretch=False, anchor="center")
        self.tree.column("line", width=70, stretch=False, anchor="center")
        self.tree.column("msg", width=900)
        self.tree.tag_configure("error", foreground=C["err"])
        self.tree.tag_configure("warning", foreground=C["warn"])
        psb = ttk.Scrollbar(pf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=psb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        psb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", self._problem_click)
        self.bnb.add(pf, text="  PROBLEMY  ")

    def _build_statusbar(self):
        sb = tk.Frame(self.root, bg=C["purple2"], height=24)
        sb.pack(fill="x", side="bottom")
        self.st_left = tk.Label(sb, text="", bg=C["purple2"], fg="#ffffff", font=("Segoe UI", 9), anchor="w")
        self.st_left.pack(side="left", padx=10)
        self.st_right = tk.Label(sb, text="", bg=C["purple2"], fg="#ffffff", font=("Segoe UI", 9), anchor="e")
        self.st_right.pack(side="right", padx=10)

    # ---- skróty ---------------------------------------------------------------
    def bind_shortcuts(self, w, is_root=False):
        def br(fn):
            return lambda e=None: (fn(), "break")[1]
        b = (w.bind_all if is_root else w.bind)
        for seq, fn in (("<Control-n>", lambda: self.new_doc(self.lang_var.get())), ("<Control-o>", self.open_dialog),
                        ("<Control-s>", self.save), ("<Control-S>", self.save_as), ("<Control-w>", self.close_current),
                        ("<Control-f>", self.find_dialog), ("<Control-g>", self.goto_dialog),
                        ("<Control-slash>", self.toggle_comment), ("<F5>", self.run_current),
                        ("<F6>", self.debug_current), ("<F7>", self.deep_analyze), ("<F9>", self.toggle_breakpoint),
                        ("<Shift-F5>", self.stop), ("<Control-plus>", lambda: self.zoom(1)),
                        ("<Control-equal>", lambda: self.zoom(1)), ("<Control-minus>", lambda: self.zoom(-1)),
                        ("<Control-0>", lambda: self.zoom(0)), ("<Control-a>", self.select_all)):
            b(seq, br(fn))
        for i, lg in enumerate(LANG_ORDER):
            b(f"<Alt-Key-{i + 1}>", br(lambda lg=lg: self.set_language(lg)))

    # ---- dokumenty --------------------------------------------------------------
    def current(self):
        try:
            sel = self.nb.select()
        except tk.TclError:
            return None
        return self.docs.get(str(sel)) if sel else None

    def _cur_text_event(self, ev):
        d = self.current()
        if d:
            d.text.event_generate(ev)

    def select_all(self):
        d = self.current()
        if d:
            d.text.tag_add("sel", "1.0", "end-1c")
            d.text.mark_set("insert", "end-1c")

    def tab_title(self, d):
        name = os.path.basename(d.path) if d.path else d.untitled_name
        return f" {name}{' ●' if d.dirty else ''} "

    def refresh_tab(self, d):
        try:
            self.nb.tab(d.frame, text=self.tab_title(d))
        except tk.TclError:
            return
        if self.current() is d:
            name = os.path.basename(d.path) if d.path else d.untitled_name
            self.root.title(f"{'● ' if d.dirty else ''}{name} — {APP}")

    def new_doc(self, lang, path=None, content=None):
        tmpl = LANGS[lang]["template"]
        if content is None:
            content = tmpl
        d = Doc(self, path, lang, content)
        if path is None:
            self.untitled_n += 1
            d.untitled_name = f"nowy_{self.untitled_n}{LANGS[lang]['ext']}"
            d.pristine_template = content
        self.docs[str(d.frame)] = d
        self.nb.add(d.frame, text=self.tab_title(d))
        self.nb.select(d.frame)
        d.text.focus_set()
        return d

    def open_dialog(self):
        paths = filedialog.askopenfilenames(
            title="Otwórz plik", initialdir=self.last_dir,
            filetypes=[("Pliki kodu", "*.py *.pyw *.cpp *.cc *.cxx *.c *.h *.hpp *.java *.js *.mjs *.html *.htm"),
                       ("Python", "*.py *.pyw"), ("C++", "*.cpp *.cc *.cxx *.c *.h *.hpp"), ("Java", "*.java"),
                       ("JavaScript", "*.js *.mjs"), ("HTML", "*.html *.htm"), ("Wszystkie pliki", "*.*")])
        for p in paths:
            self.open_path(p)

    def find_doc_by_path(self, path):
        np_ = os.path.normcase(os.path.abspath(path))
        for d in self.docs.values():
            if d.path and os.path.normcase(os.path.abspath(d.path)) == np_:
                return d
        return None

    def open_path(self, path, line=None):
        path = os.path.abspath(path)
        d = self.find_doc_by_path(path)
        if d:
            self.nb.select(d.frame)
        else:
            try:
                content = read_text_file(path)
            except Exception as e:
                messagebox.showerror(APP, f"Nie można otworzyć pliku:\n{path}\n\n{e}")
                return None
            lang = EXT2LANG.get(os.path.splitext(path)[1].lower(), self.lang_var.get())
            cur = self.current()
            d = self.new_doc(lang, path=path, content=content)
            if cur and cur.path is None and not cur.dirty and cur.src() == cur.pristine_template:
                self.close_doc(cur, force=True)
            self.last_dir = os.path.dirname(path)
        if line:
            d.goto(line)
        return d

    def write_doc(self, d, path):
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(d.src())
        except Exception as e:
            messagebox.showerror(APP, f"Nie udało się zapisać pliku:\n{e}")
            return False
        d.path = path
        d.dirty = False
        self.last_dir = os.path.dirname(path)
        self.refresh_tab(d)
        return True

    def save(self, d=None):
        d = d or self.current()
        if not d:
            return False
        if not d.path:
            return self.save_as(d)
        return self.write_doc(d, d.path)

    def save_as(self, d=None):
        d = d or self.current()
        if not d:
            return False
        ext = LANGS[d.lang]["ext"]
        initial = os.path.basename(d.path) if d.path else d.untitled_name
        p = filedialog.asksaveasfilename(title="Zapisz jako", initialdir=self.last_dir, initialfile=initial,
                                         defaultextension=ext,
                                         filetypes=[(d.lang, "*" + ext), ("Wszystkie pliki", "*.*")])
        if not p:
            return False
        if not self.write_doc(d, p):
            return False
        lang = EXT2LANG.get(os.path.splitext(p)[1].lower())
        if lang and lang != d.lang:
            d.set_lang(lang)
            self.lang_var.set(lang)
        return True

    def ensure_saved(self, d):
        if d.path and not d.dirty:
            return True
        return self.save(d)

    def close_current(self):
        d = self.current()
        if d:
            self.close_doc(d)

    def _middle_close(self, e):
        try:
            idx = self.nb.index(f"@{e.x},{e.y}")
        except tk.TclError:
            return
        frame = self.nb.tabs()[idx]
        d = self.docs.get(str(frame))
        if d:
            self.close_doc(d)

    def close_doc(self, d, force=False):
        if d.dirty and not force:
            name = os.path.basename(d.path) if d.path else d.untitled_name
            r = messagebox.askyesnocancel(APP, f"Zapisać zmiany w „{name}”?")
            if r is None:
                return False
            if r and not self.save(d):
                return False
        d.ac_hide()
        self.nb.forget(d.frame)
        self.docs.pop(str(d.frame), None)
        d.frame.destroy()
        if not self.docs:
            self.new_doc(self.lang_var.get())
        return True

    def on_exit(self):
        for d in list(self.docs.values()):
            if d.dirty:
                self.nb.select(d.frame)
                if not self.close_doc(d):
                    return
        self.stop()
        self.root.destroy()

    # ---- język --------------------------------------------------------------------
    def set_language(self, lg):
        self.lang_var.set(lg)
        self.on_lang_change()

    def on_lang_change(self):
        d = self.current()
        if not d:
            return
        lg = self.lang_var.get()
        old = d.lang
        if lg == old:
            return
        if d.path is None and not d.dirty and d.src() == d.pristine_template:
            d.pristine_template = LANGS[lg]["template"]
            d.untitled_name = os.path.splitext(d.untitled_name)[0] + LANGS[lg]["ext"]
            d.lang = lg
            d.set_content(LANGS[lg]["template"])
        else:
            d.set_lang(lg)
        self.refresh_tab(d)
        self.update_status(d)

    def on_tab_changed(self, e=None):
        for d in self.docs.values():
            d.ac_hide()
        d = self.current()
        if not d:
            return
        self.lang_var.set(d.lang)
        self.refresh_tab(d)
        self.show_problems(d)
        self.update_status(d)
        d.text.focus_set()
        d.draw_gutter()

    # ---- status / problemy ------------------------------------------------------------
    def update_status(self, d):
        if d is not self.current():
            return
        ln, col = d.text.index("insert").split(".")
        errs = sum(1 for p in d.all_problems() if p.sev == "error")
        warns = sum(1 for p in d.all_problems() if p.sev == "warning")
        self.st_left.configure(text=f"Ln {ln}, Kol {int(col) + 1}    ✖ {errs}   ⚠ {warns}")
        self.st_right.configure(text=f"{d.lang}    UTF-8    Spacje: 4")
        try:
            self.bnb.tab(1, text=f"  PROBLEMY ({errs + warns})  " if errs + warns else "  PROBLEMY  ")
        except tk.TclError:
            pass

    def show_problems(self, d):
        self.tree.delete(*self.tree.get_children())
        for p in d.all_problems():
            self.tree.insert("", "end", values=("✖" if p.sev == "error" else "⚠", p.line, p.msg), tags=(p.sev,))
        self.update_status(d)

    def _problem_click(self, e):
        sel = self.tree.selection()
        d = self.current()
        if sel and d:
            d.goto(int(self.tree.item(sel[0], "values")[1]))

    # ---- edycja pomocnicza ------------------------------------------------------------
    def toggle_comment(self):
        d = self.current()
        if d:
            d.toggle_comment()

    def force_complete(self):
        d = self.current()
        if d:
            d.ac_show(force=True)

    def toggle_breakpoint(self):
        d = self.current()
        if not d:
            return
        ln = int(d.text.index("insert").split(".")[0])
        d.breakpoints.symmetric_difference_update({ln})
        d.draw_gutter()

    def zoom(self, delta):
        size = self.font.cget("size")
        size = 12 if delta == 0 else max(7, min(40, size + delta))
        self.font.configure(size=size)
        self.gfont.configure(size=max(7, size - 2))
        for d in self.docs.values():
            d.apply_tabs()
            d.draw_gutter()

    def goto_dialog(self):
        d = self.current()
        if not d:
            return
        n = simpledialog.askinteger("Idź do linii", "Numer linii:", parent=self.root, minvalue=1)
        if n:
            d.goto(n)

    def find_dialog(self):
        d = self.current()
        if not d:
            return
        if getattr(self, "_find_win", None) and self._find_win.winfo_exists():
            self._find_win.lift()
            self._find_win.focus_force()
            return
        win = tk.Toplevel(self.root)
        self._find_win = win
        win.title("Znajdź / Zamień")
        win.configure(bg=C["panel"])
        win.transient(self.root)
        win.resizable(False, False)
        case = tk.BooleanVar(value=False)

        def lab(r, txt):
            tk.Label(win, text=txt, bg=C["panel"], fg=C["dim"]).grid(row=r, column=0, padx=10, pady=6, sticky="e")

        def ent(r):
            e = tk.Entry(win, width=32, bg=C["bg"], fg=C["fg"], insertbackground=C["green"], bd=0, relief="flat",
                         highlightthickness=1, highlightbackground=C["line"], highlightcolor=C["purple"])
            e.grid(row=r, column=1, columnspan=3, padx=6, pady=6, ipady=3)
            return e
        lab(0, "Znajdź:")
        fe = ent(0)
        lab(1, "Zamień na:")
        re_ = ent(1)
        tk.Checkbutton(win, text="Uwzględnij wielkość liter", variable=case, bg=C["panel"], fg=C["fg"],
                       selectcolor=C["bg"], activebackground=C["panel"], activeforeground=C["green"],
                       bd=0).grid(row=2, column=1, columnspan=3, sticky="w", padx=6)
        sel_text = ""
        if d.text.tag_ranges("sel"):
            sel_text = d.text.get("sel.first", "sel.last")
        if sel_text and "\n" not in sel_text:
            fe.insert(0, sel_text)

        def cur():
            return self.current()

        def find(back=False, wrap=True):
            dd = cur()
            pat = fe.get()
            if not dd or not pat:
                return False
            t = dd.text
            if back:
                start = t.index("sel.first") if t.tag_ranges("sel") else t.index("insert")
                pos = t.search(pat, start, stopindex="1.0", backwards=True, nocase=not case.get())
                if not pos and wrap:
                    pos = t.search(pat, "end-1c", stopindex="1.0", backwards=True, nocase=not case.get())
            else:
                start = t.index("sel.last") if t.tag_ranges("sel") else t.index("insert")
                pos = t.search(pat, start, stopindex="end", nocase=not case.get())
                if not pos and wrap:
                    pos = t.search(pat, "1.0", stopindex="end", nocase=not case.get())
            if not pos:
                return False
            t.tag_remove("sel", "1.0", "end")
            t.tag_add("sel", pos, f"{pos}+{len(pat)}c")
            t.mark_set("insert", f"{pos}+{len(pat)}c")
            t.see(pos)
            dd.after_cursor()
            return True

        def replace_one():
            dd = cur()
            if not dd:
                return
            t = dd.text
            pat = fe.get()
            if t.tag_ranges("sel"):
                s = t.get("sel.first", "sel.last")
                if (s == pat) if case.get() else (s.lower() == pat.lower()):
                    t.edit_separator()
                    t.delete("sel.first", "sel.last")
                    t.insert("insert", re_.get())
                    t.edit_separator()
            find()

        def replace_all():
            dd = cur()
            pat = fe.get()
            if not dd or not pat:
                return
            t = dd.text
            rep = re_.get()
            pos, n = "1.0", 0
            t.edit_separator()
            while True:
                pos = t.search(pat, pos, stopindex="end", nocase=not case.get())
                if not pos:
                    break
                t.delete(pos, f"{pos}+{len(pat)}c")
                t.insert(pos, rep)
                pos = f"{pos}+{len(rep)}c"
                n += 1
                if n > 100000:
                    break
            t.edit_separator()
            self.out(f"Zamieniono {n} wystąpień.\n", "info")

        def mkbtn(txt, cmd, col):
            tk.Button(win, text=txt, command=cmd, bg=C["line"], fg=col, bd=0, relief="flat", padx=10, pady=4,
                      activebackground=C["purple2"], activeforeground="#ffffff",
                      cursor="hand2").grid(row=3, column=mkbtn.c, padx=4, pady=10)
            mkbtn.c += 1
        mkbtn.c = 0
        # kolumny 0..3: Wstecz | Dalej | Zamień | Wszystkie
        mkbtn("◀ Wstecz", lambda: find(True), C["fg"])
        mkbtn("Dalej ▶", find, C["green"])
        mkbtn("Zamień", replace_one, C["purple"])
        mkbtn("Wszystkie", replace_all, C["purple"])
        fe.bind("<Return>", lambda e: find())
        fe.focus_set()
        win.bind("<Escape>", lambda e: win.destroy())

    # ---- wyjście / uruchamianie -----------------------------------------------------------
    def clear_out(self):
        o = self.output
        o.configure(state="normal")
        o.delete("1.0", "end")
        o.configure(state="disabled")

    def out(self, text, tag=None):
        for a, b in self.path_map.items():
            text = text.replace(a, b)
        o = self.output
        o.configure(state="normal")
        start = o.index("end-1c")
        o.insert("end", text, tag)
        if not tag:
            self._colorize(start, text)
        self._linkify(start, text)
        if int(o.index("end-1c").split(".")[0]) > 5000:
            o.delete("1.0", "1000.0")
        o.see("end")
        o.configure(state="disabled")

    def _colorize(self, start, text):
        o = self.output
        off = 0
        for line in text.splitlines(True):
            tag = None
            if re.search(r"(?i)traceback|error|exception|fatal|undefined reference", line):
                tag = "err"
            elif re.search(r"(?i)warning", line):
                tag = "warn"
            if tag:
                o.tag_add(tag, f"{start}+{off}c", f"{start}+{off + len(line)}c")
            off += len(line)

    _LINK_RX = [re.compile(r'File "(.+?)", line (\d+)'),
                re.compile(r'((?:[A-Za-z]:)?[^\s:"\'()<>|*?]+?\.(?:py|cpp|cc|cxx|c|h|hpp|java|js|mjs|html?)):(\d+)(?::\d+)?')]

    def _linkify(self, start, text):
        o = self.output
        for rx in self._LINK_RX:
            for m in rx.finditer(text):
                self.link_n += 1
                name = f"lnk{self.link_n}"
                o.tag_configure(name, foreground=C["green"], underline=True)
                o.tag_add(name, f"{start}+{m.start()}c", f"{start}+{m.end()}c")
                o.tag_bind(name, "<Button-1>", lambda e, p=m.group(1), l=int(m.group(2)): self.goto_file(p, l))
                o.tag_bind(name, "<Enter>", lambda e: o.configure(cursor="hand2"))
                o.tag_bind(name, "<Leave>", lambda e: o.configure(cursor="xterm"))

    def goto_file(self, path, line):
        cand = [path]
        d = self.current()
        if d and d.path:
            cand.append(os.path.join(os.path.dirname(d.path), os.path.basename(path)))
        for c in cand:
            if os.path.isfile(c):
                self.open_path(c, line)
                return
        base = os.path.basename(path)
        for dd in self.docs.values():
            if dd.path and os.path.basename(dd.path) == base:
                self.nb.select(dd.frame)
                dd.goto(line)
                return

    def need(self, tool):
        p = find_python() if tool == "python" else shutil.which(tool)
        if not p:
            self.show_out_tab()
            self.out(f"✖ Nie znaleziono '{tool}'. {TOOL_HINTS.get(tool, '')}\n", "err")
            self.set_status_msg(f"Brak narzędzia: {tool}")
        return p

    def set_status_msg(self, msg):
        self.st_left.configure(text=msg)

    def show_out_tab(self):
        self.bnb.select(0)

    def exec_steps(self, steps, cwd, label, on_success=None):
        if self.running:
            self.stop()
            time.sleep(0.1)
        self.clear_out()
        self.show_out_tab()
        self.out(f"▶ {label}\n", "info")
        self.running = True
        self.t0 = time.time()
        threading.Thread(target=self._worker, args=(steps, cwd, on_success), daemon=True).start()

    def _worker(self, steps, cwd, on_success):
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        ok = True
        rc = 0
        for cmd in steps:
            self.q.put(("info", "$ " + " ".join(shlex.quote(c) if " " in c else c for c in cmd) + "\n"))
            try:
                p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, env=child_env(), creationflags=flags)
            except Exception as e:
                self.q.put(("err", f"Nie można uruchomić: {e}\n"))
                ok, rc = False, -1
                break
            self.proc = p
            dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
            try:
                while True:
                    data = os.read(p.stdout.fileno(), 4096)
                    if not data:
                        break
                    self.q.put(("out", dec.decode(data)))
            except Exception:
                pass
            rc = p.wait()
            if rc != 0:
                ok = False
                break
        self.proc = None
        self.q.put(("done", ok, rc, on_success))

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "out":
                    self.out(item[1])
                elif kind in ("info", "err"):
                    self.out(item[1], kind)
                elif kind == "done":
                    _, ok, rc, cb = item
                    self.running = False
                    dt = time.time() - getattr(self, "t0", time.time())
                    if ok:
                        self.out(f"\n✔ Zakończono pomyślnie ({dt:.2f} s)\n", "ok")
                        if cb:
                            cb()
                    else:
                        self.out(f"\n✖ Zakończono z błędem (kod {rc})\n", "err")
        except queue.Empty:
            pass
        try:
            self.stop_btn.configure(state="normal" if self.running else "disabled")
        except tk.TclError:
            return
        self.root.after(40, self._poll)

    def stop(self):
        p = self.proc
        if p and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass

    def send_stdin(self, e=None):
        line = self.stdin.get()
        self.stdin.delete(0, "end")
        p = self.proc
        self.out(line + "\n", "stdin")
        if p and p.poll() is None:
            try:
                p.stdin.write((line + "\n").encode("utf-8"))
                p.stdin.flush()
            except Exception:
                pass

    def _tmpdir(self):
        return tempfile.mkdtemp(prefix="coddy_run_")

    def _build_plan(self, d, debug):
        """Zwraca (steps, cwd, final) gdzie steps to polecenia budowania/uruchomienia (run),
        a final to funkcja wywoływana po budowie (debug)."""
        lang, path = d.lang, d.path
        folder = os.path.dirname(path)
        src = d.src()
        name = os.path.basename(path)
        bps = sorted(d.breakpoints)
        if lang == "Python":
            py = self.need("python")
            if not py:
                return None
            if not debug:
                return [[py, "-u", path]], folder, None
            args = [py, "-m", "pdb"]
            for b in bps:
                args += ["-c", f"b {path}:{b}"]
            if bps:
                args += ["-c", "continue"]
            args.append(path)
            return [], folder, lambda: self._launch_debugger(args, folder, "pdb: n=następna linia, s=wejdź, c=dalej, p wyr=wartość, l=kod, q=wyjście")
        if lang == "JavaScript":
            node = self.need("node")
            if not node:
                return None
            if not debug:
                return [[node, path]], folder, None
            tmp = self._tmpdir()
            lines = src.split("\n")
            for b in bps:
                if 1 <= b <= len(lines):
                    lines[b - 1] = "debugger; " + lines[b - 1]
            tfile = os.path.join(tmp, name)
            with open(tfile, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return [], folder, lambda: self._launch_debugger([node, "inspect", tfile], folder,
                                                             "node inspect: c=dalej, n=następna linia, s=wejdź, repl=wartości, .exit=wyjście")
        if lang == "C++":
            is_c = path.lower().endswith(".c")
            cc = self.need("gcc" if is_c else "g++")
            if not cc:
                return None
            tmp = self._tmpdir()
            exe = os.path.join(tmp, "program" + (".exe" if os.name == "nt" else ""))
            build = [cc, "-std=c11" if is_c else "-std=c++17", "-g", "-O0", "-Wall", path, "-o", exe]
            if not debug:
                return [build, [exe]], folder, None
            gdb = self.need("gdb")
            if not gdb:
                return None
            args = [gdb, "-q"]
            for b in bps:
                args += ["-ex", f"break {name}:{b}"]
            if not bps:
                args += ["-ex", "break main"]
            args += ["-ex", "run", "--args", exe]
            return [build], folder, lambda: self._launch_debugger(args, folder, "gdb: n=następna linia, s=wejdź, c=dalej, p zm=wartość, bt=stos, q=wyjście")
        if lang == "Java":
            javac = self.need("javac")
            java = self.need("java")
            if not javac or not java:
                return None
            cls = java_main_class(src, os.path.splitext(name)[0])
            tmp = self._tmpdir()
            tsrc = os.path.join(tmp, cls + ".java")
            with open(tsrc, "w", encoding="utf-8") as f:
                f.write(src)
            self.path_map[tsrc] = path
            build = [javac, "-g", "-encoding", "UTF-8", "-d", tmp, tsrc]
            if not debug:
                return [build, [java, "-cp", tmp, cls]], folder, None
            jdb = self.need("jdb")
            if not jdb:
                return None
            cmds = [f"stop at {cls}:{b}" for b in bps] or [f"stop in {cls}.main"]
            for fn in (".jdbrc", "jdb.ini"):
                with open(os.path.join(tmp, fn), "w", encoding="utf-8") as f:
                    f.write("\n".join(cmds + ["run"]) + "\n")
            args = [jdb, "-sourcepath", tmp, "-classpath", tmp, cls]
            return [build], tmp, lambda: self._launch_debugger(args, tmp, "jdb: next=następna linia, step=wejdź, cont=dalej, print zm=wartość, quit=wyjście")
        return None

    def _launch_debugger(self, args, cwd, tip):
        self.out(f"\n◉ Uruchamiam debugger w nowym oknie konsoli.\n  {tip}\n", "info")
        try:
            if not open_terminal(args, cwd):
                self.out("✖ Nie znaleziono emulatora terminala do uruchomienia debuggera.\n", "err")
        except Exception as e:
            self.out(f"✖ Nie udało się uruchomić debuggera: {e}\n", "err")

    def run_current(self):
        d = self.current()
        if not d:
            return
        if not self.ensure_saved(d):
            return
        if d.lang == "HTML5":
            self.show_out_tab()
            self.clear_out()
            self.out("▶ Otwieram w przeglądarce: " + d.path + "\n", "info")
            webbrowser.open(Path(d.path).as_uri())
            return
        self.path_map = {}
        plan = self._build_plan(d, debug=False)
        if not plan:
            return
        steps, cwd, _ = plan
        self.exec_steps(steps, cwd, f"Uruchamianie {os.path.basename(d.path)} ({d.lang})")

    def debug_current(self):
        d = self.current()
        if not d:
            return
        if not self.ensure_saved(d):
            return
        if d.lang == "HTML5":
            self.run_current()
            self.out("Debugowanie HTML/JS: w przeglądarce naciśnij F12 (Narzędzia deweloperskie → Sources).\n", "info")
            return
        self.path_map = {}
        plan = self._build_plan(d, debug=True)
        if not plan:
            return
        steps, cwd, final = plan
        if steps:
            self.exec_steps(steps, cwd, f"Budowanie do debugowania ({d.lang})", on_success=final)
        else:
            self.clear_out()
            self.show_out_tab()
            self.out(f"◉ Debugowanie {os.path.basename(d.path)} ({d.lang})\n", "info")
            if d.breakpoints:
                self.out("Punkty przerwania w liniach: " + ", ".join(map(str, sorted(d.breakpoints))) + "\n", "info")
            final()

    def deep_analyze(self):
        d = self.current()
        if not d:
            return
        d.run_quick()
        src, lang = d.src(), d.lang
        self.set_status_msg("Analiza kodu…")

        def work():
            res = deep_check(lang, src)
            self.root.after(0, lambda: self._deep_done(d, src, res))
        threading.Thread(target=work, daemon=True).start()

    def _deep_done(self, d, src, res):
        probs, note = res
        if d.src() == src:
            d.deep_problems = probs
            d.apply_problems()
        self.bnb.select(1)
        n = len(d.all_problems())
        msg = note or ("Analiza zakończona: brak problemów ✔" if n == 0 else f"Analiza zakończona: {n} problem(ów)")
        self.set_status_msg(msg)
        if note:
            self.out("ℹ " + note + "\n", "info")

    # ---- pomoc ---------------------------------------------------------------------------
    def show_help(self):
        messagebox.showinfo(APP + " – skróty", (
            "Ctrl+N  nowy plik          Ctrl+O  otwórz\n"
            "Ctrl+S  zapisz             Ctrl+Shift+S  zapisz jako\n"
            "Ctrl+W  zamknij kartę      Ctrl+F  znajdź/zamień\n"
            "Ctrl+G  idź do linii       Ctrl+/  komentarz\n"
            "Ctrl+Spacja  podpowiedzi   Tab/Shift+Tab  wcięcia\n"
            "F5  uruchom                F6  debuguj\n"
            "F7  analiza kompilatorem   F9  punkt przerwania\n"
            "Shift+F5  stop             Ctrl +/-/0  zoom\n"
            "Alt+1..5  język (Python, C++, Java, JS, HTML5)\n\n"
            "Klik w lewy margines = punkt przerwania.\n"
            "Klik w błąd w oknie wyjścia = skok do linii."))

    def show_about(self):
        messagebox.showinfo("O programie", f"{APP} {VERSION}\nOffline edytor kodu: Python, C++, Java, JavaScript, HTML5.\n"
                                           "Fioletowo-zielono-czarny motyw.")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--make-icon":
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coddy.ico")
        write_ico(out, 256)
        print("Zapisano", out)
        return
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    App(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
