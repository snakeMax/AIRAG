"""Interactive explainers: AI-written pages are cleaned before they're shown (see airag/interactive.py)."""
from airag.interactive import SAFE_MARK, clean_html, safe
from airag.jsguard import guard_loops


def test_rules_come_before_anything_the_ai_wrote():
    out = clean_html('<html><script>fetch("x")</script><head></head><body>hi</body></html>')
    assert out.index("Content-Security-Policy") < out.index('fetch("x")')
    assert out.index("__airagGuard") < out.index('fetch("x")')
    assert "connect" not in out.split("Content-Security-Policy")[1].split(">")[0] or "default-src 'none'" in out


def test_strips_things_that_reach_the_internet_without_scripts():
    evil = ('<html><head><meta http-equiv="refresh" content="0;url=https://x.example"><base href="https://x.example/">'
            '<link rel="dns-prefetch" href="//x.example"><meta http-equiv="Content-Security-Policy" content="default-src *">'
            '</head><body><iframe src="https://x.example"></iframe><object data="x"></object><embed src="x"></body></html>')
    out = clean_html(evil).lower()
    for bad in ('http-equiv="refresh"', "<base", "<link", "<iframe", "<object", "<embed", "default-src *"):
        assert bad not in out


def test_loops_are_guarded_but_strings_and_regexes_are_not_touched():
    code = ('const s = "while(1){}"; // for(;;){}\n'
            'const r = /for\\(;;\\){/; const t = `do {${"{"}`;\n'
            'for (let i = 0; i < 3; i++) { a(); }\nwhile (x) { b(); }\ndo { c(); } while (y);\nobj.for(1); z = p / q / w;')
    out = guard_loops(code)
    assert out.count("__airagGuard") == 3
    assert '"while(1){}"' in out and "// for(;;){}" in out and "/for\\(;;\\){/" in out and '`do {${"{"}`' in out


def test_old_explainers_are_cleaned_once():
    old = "<html><head></head><body><script>while(true){}</script></body></html>"
    once = safe(old)
    assert SAFE_MARK in once and "__airagGuard())break" in once
    assert safe(once) == once
