"""
sexp_parser.py — Trad-Four roadmap module
S-expression tokenizer and parser for Impro-Visor dictionary files.

Handles the same input as Impro-Visor's polya.Tokenizer:
  - /* ... */ block comments
  - // ... line comments
  - Nested parenthesized lists
  - Atoms (strings, numbers)

Usage:
    from python.roadmap.sexp_parser import parse_file, parse_string

    exprs = parse_file('/usr/share/impro-visor/vocab/My.dictionary')
    for expr in exprs:
        print(expr)   # each is a list or atom

Output format:
    Atoms  → str
    Lists  → list of atoms/lists
    e.g. '(defbrick Starlight Major Cadence C (chord Dm7 1) (chord G7 1))'
    →    ['defbrick', 'Starlight', 'Major', 'Cadence', 'C',
           ['chord', 'Dm7', '1'], ['chord', 'G7', '1']]
"""

import re
from typing import Union

SExp = Union[str, list]


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# Token patterns in priority order
_TOKEN_RE = re.compile(r"""
    /\*.*?\*/           |   # block comment
    //[^\n]*            |   # line comment
    \(                  |   # open paren
    \)                  |   # close paren
    [^\s()/]+           |   # atom (anything else)
    \s+                     # whitespace (ignored)
""", re.VERBOSE | re.DOTALL)


def tokenize(text: str) -> list[str]:
    """
    Tokenize an S-expression string, stripping comments and whitespace.
    Returns a list of token strings: '(', ')', or atom strings.
    """
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        tok = m.group(0)
        if tok.startswith('/*') or tok.startswith('//'):
            continue    # strip comments
        if tok.strip() == '':
            continue    # strip whitespace
        tokens.append(tok)
    return tokens


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class ParseError(Exception):
    pass


def _parse_tokens(tokens: list[str], pos: int) -> tuple[SExp, int]:
    """
    Recursive descent parser over a token list.
    Returns (expression, next_position).
    """
    if pos >= len(tokens):
        raise ParseError(f"Unexpected end of input at position {pos}")

    tok = tokens[pos]

    if tok == ')':
        raise ParseError(f"Unexpected ')' at position {pos}")

    if tok == '(':
        # Parse a list
        items = []
        pos += 1
        while pos < len(tokens) and tokens[pos] != ')':
            item, pos = _parse_tokens(tokens, pos)
            items.append(item)
        if pos >= len(tokens):
            raise ParseError("Unclosed '(' — reached end of input")
        pos += 1   # consume ')'
        return items, pos

    else:
        # Atom
        return tok, pos + 1


def parse_string(text: str) -> list[SExp]:
    """
    Parse a string containing zero or more S-expressions.
    Returns a list of top-level expressions.
    """
    tokens = tokenize(text)
    exprs = []
    pos = 0
    while pos < len(tokens):
        try:
            expr, pos = _parse_tokens(tokens, pos)
            exprs.append(expr)
        except ParseError as e:
            raise ParseError(f"Parse error: {e}\nNear token {pos}: "
                             f"{tokens[max(0,pos-2):pos+3]}")
    return exprs


def parse_file(path: str) -> list[SExp]:
    """
    Parse an Impro-Visor dictionary file.
    Returns a list of top-level S-expressions.
    """
    with open(path, encoding='utf-8', errors='replace') as f:
        text = f.read()
    return parse_string(text)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def is_list(expr: SExp) -> bool:
    return isinstance(expr, list)


def is_atom(expr: SExp) -> bool:
    return isinstance(expr, str)


def head(expr: list) -> str:
    """Return the first element of a list expression (the tag/keyword)."""
    return expr[0] if expr else ''


def tail(expr: list) -> list:
    """Return all elements after the first."""
    return expr[1:] if len(expr) > 1 else []


def to_str(expr: SExp, indent: int = 0) -> str:
    """Pretty-print an S-expression."""
    if is_atom(expr):
        return expr
    inner = ' '.join(to_str(e) for e in expr)
    if len(inner) < 60:
        return f'({inner})'
    lines = [f'({to_str(expr[0])}']
    for e in expr[1:]:
        lines.append('  ' * (indent + 1) + to_str(e, indent + 1))
    lines[-1] += ')'
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else \
        '/usr/share/impro-visor/vocab/My.dictionary'
    exprs = parse_file(path)
    print(f"Parsed {len(exprs)} top-level expressions from {path}")
    print(f"\nFirst 3:")
    for e in exprs[:3]:
        print(' ', to_str(e))
    print(f"\nAll tags: {sorted(set(head(e) for e in exprs if is_list(e)))}")