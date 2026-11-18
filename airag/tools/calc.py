"""Calculator: arithmetic, units of numbers, statistics and algebra (SymPy), without running code.

The expression is checked character by character and name by name before SymPy reads it: only
numbers, operators, brackets, commas, single-letter or short variable names and a list of maths
functions are allowed. Python features (dots after names, underscores, quotes, imports) are refused.
"""
from __future__ import annotations

import asyncio
import re
from typing import Tuple

ALLOWED_FUNCS = {
    # algebra & calculus
    "solve", "simplify", "expand", "factor", "diff", "integrate", "limit", "summation", "Sum", "Eq", "nsolve",
    "apart", "together", "cancel", "series", "Derivative", "Integral", "Matrix", "det",
    # functions
    "sqrt", "cbrt", "root", "exp", "log", "ln", "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "sinh", "cosh",
    "tanh", "Abs", "abs", "floor", "ceiling", "round", "factorial", "binomial", "gcd", "lcm", "mod", "Mod", "min",
    "max", "Min", "Max", "re", "im", "sign", "rad", "deg",
    # constants
    "pi", "E", "I", "oo", "inf",
    # statistics (handled below)
    "mean", "median", "stdev", "variance", "total",
}
_TOKEN = re.compile(r"[A-Za-z]+[0-9]*")
_SAFE_CHARS = re.compile(r"^[0-9A-Za-z\s+\-*/^().,=<>%!\[\]]*$")
MAX_LEN = 600


def check(expr: str) -> str:
    e = (expr or "").strip()
    if not e:
        raise ValueError("empty expression")
    if len(e) > MAX_LEN:
        raise ValueError("expression too long")
    e = e.replace("×", "*").replace("÷", "/").replace("−", "-").replace("·", "*").replace("²", "**2").replace("³", "**3")
    if not _SAFE_CHARS.match(e):
        raise ValueError("only numbers, letters, + - * / ^ ( ) , = and brackets are allowed")
    if re.search(r"[A-Za-z_]\s*\.", e):
        raise ValueError("dots are only allowed inside numbers")
    if re.search(r"\*\*\s*\(?\s*\d{5,}|\^\s*\(?\s*\d{5,}", e):
        raise ValueError("exponent too large")
    for tok in _TOKEN.findall(e):
        if tok in ALLOWED_FUNCS or len(tok) <= 3:     # functions, or short variable names (x, y, v0, abc)
            continue
        raise ValueError(f"unknown name '{tok}'")
    return e


def _evaluate(e: str) -> Tuple[str, str]:
    import statistics
    import sympy
    from sympy.parsing.sympy_parser import (convert_xor, implicit_multiplication_application, parse_expr,
                                            standard_transformations)
    ns = {n: getattr(sympy, n) for n in ALLOWED_FUNCS if hasattr(sympy, n)}
    ns.update({"ln": sympy.log, "abs": sympy.Abs, "inf": sympy.oo, "round": lambda x, n=0: sympy.Float(round(float(x), int(n))),
               "rad": lambda d: d * sympy.pi / 180, "deg": lambda r: r * 180 / sympy.pi, "mod": sympy.Mod,
               "min": sympy.Min, "max": sympy.Max, "cbrt": sympy.cbrt,
               "mean": lambda *a: sympy.nsimplify(statistics.fmean(float(x) for x in a)),
               "median": lambda *a: sympy.nsimplify(statistics.median(float(x) for x in a)),
               "stdev": lambda *a: sympy.Float(statistics.stdev(float(x) for x in a)),
               "variance": lambda *a: sympy.Float(statistics.variance(float(x) for x in a)),
               "total": lambda *a: sum(a)})
    glob = {"__builtins__": {}}
    glob.update({k: getattr(sympy, k) for k in ("Integer", "Float", "Rational", "Symbol", "Function")})
    tr = standard_transformations + (implicit_multiplication_application, convert_xor)
    e = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", e)
    if "=" in e and not re.search(r"[<>!=]=|Eq\(", e) and not e.startswith("solve"):
        left, right = e.split("=", 1)          # "2x + 3 = 11" -> solve it
        expr = parse_expr(f"({left})-({right})", local_dict=ns, global_dict=glob, transformations=tr)
        free = sorted(expr.free_symbols, key=str)
        result = sympy.solve(expr, free[0]) if free else sympy.simplify(expr) == 0
    else:
        result = parse_expr(e, local_dict=ns, global_dict=glob, transformations=tr)
        if hasattr(result, "doit"):
            result = result.doit()
    exact = str(result)
    approx = ""
    def whole(r):
        return getattr(r, "is_Integer", False) or getattr(r, "is_Boolean", False) or isinstance(r, bool)
    try:
        if isinstance(result, (list, tuple)):
            approx = "" if all(whole(r) for r in result) else ", ".join(str(sympy.N(r, 10)) for r in result)
        elif whole(result):
            approx = ""
        else:
            n = sympy.N(result, 12)
            approx = str(n) if n != result else ""
    except Exception:
        approx = ""
    return exact, approx


async def calculate(expr: str, timeout: float = 8.0) -> Tuple[str, str, str]:
    """-> (checked expression, exact result, decimal approximation)"""
    e = check(expr)
    exact, approx = await asyncio.wait_for(asyncio.to_thread(_evaluate, e), timeout)
    return e, exact, approx
