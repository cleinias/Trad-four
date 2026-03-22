"""
converter.py — Trad-Four Phase 3
Convert Impro-Visor .grammar files to JSON for the SuperCollider engine.

Parses the S-expression grammar format, extracts parameters, P rules,
BRICK rules, START rules, Cluster rules, and Q rules. Handles three
note encoding types: simple terminals (C8), X intervals (X b6 8),
and slopes (slope -3 -1 C8 L8 C8).

Usage:
    from python.grammar.converter import convert_grammar

    data = convert_grammar('/path/to/LesterYoung.grammar')

CLI:
    python -m python.grammar.converter LesterYoung
    python -m python.grammar.converter data/grammars/CharlieParker.grammar
"""

import json
import re
import sys
from pathlib import Path

from python.roadmap.sexp_parser import parse_file, is_list, is_atom


# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------

def parse_duration(dur_str: str) -> float:
    """
    Parse an Impro-Visor duration string to beats.

    Subdivision-based: 1=whole(4), 2=half(2), 4=quarter(1), 8=eighth(0.5),
    16=sixteenth(0.25), 32=thirty-second(0.125).
    Additive: '4+8' = 1.0 + 0.5 = 1.5 (dotted quarter)
    Divisive: '8/3' = 0.5 / 3 ≈ 0.167 (triplet eighth)
    Combined: '4+8/3' = 1.0 + 0.167

    Formula per component: beats = 4.0 / N, with optional /D divisor.
    """
    total = 0.0
    for part in dur_str.split('+'):
        part = part.strip()
        if '/' in part:
            num, denom = part.split('/', 1)
            total += 4.0 / float(num) / float(denom)
        else:
            total += 4.0 / float(part)
    return total


# ---------------------------------------------------------------------------
# Note parsing
# ---------------------------------------------------------------------------

# Regex for simple terminal: letter(s) + duration, e.g. C8, R2+4, L16/3
_SIMPLE_RE = re.compile(r'^([CLSAXRH])(\d.*)$')


def parse_note(token):
    """
    Parse a single note token (atom string) into a dict.

    Returns:
        {"type": "C", "dur": 0.5}         for simple terminal 'C8'
        {"type": "R", "dur": 2.0}          for rest 'R2'
        None if not a recognized note token
    """
    m = _SIMPLE_RE.match(token)
    if m:
        return {"type": m.group(1), "dur": parse_duration(m.group(2))}
    return None


def parse_x_interval(expr):
    """
    Parse an X-interval S-expression: (X degree duration)
    e.g. ['X', 'b6', '8'] → {"type": "X", "degree": "b6", "dur": 0.5}
    """
    if is_list(expr) and len(expr) == 3 and expr[0] == 'X':
        return {
            "type": "X",
            "degree": expr[1],
            "dur": parse_duration(expr[2]),
        }
    return None


def parse_slope(expr):
    """
    Parse a slope S-expression: (slope start end note1 note2 ...)
    e.g. ['slope', '-3', '-1', 'C8', 'L8', 'C8']
    → {"type": "slope", "start": -3, "end": -1, "notes": [...]}
    """
    if is_list(expr) and len(expr) >= 4 and expr[0] == 'slope':
        notes = []
        for tok in expr[3:]:
            n = parse_note(tok) if is_atom(tok) else None
            if n:
                notes.append(n)
            else:
                # Could be an X-interval inside a slope
                x = parse_x_interval(tok) if is_list(tok) else None
                if x:
                    notes.append(x)
        return {
            "type": "slope",
            "start": int(expr[1]),
            "end": int(expr[2]),
            "notes": notes,
        }
    return None


def parse_note_sequence(elements):
    """
    Parse a sequence of note elements (the RHS body of a BRICK or Q rule).

    Each element is either:
    - An atom: simple terminal like 'C8', 'R2+4'
    - A list starting with 'X': X-interval like ['X', 'b6', '8']
    - A list starting with 'slope': slope contour

    Returns a list of note dicts.
    """
    notes = []
    for elem in elements:
        if is_atom(elem):
            n = parse_note(elem)
            if n:
                notes.append(n)
        elif is_list(elem):
            x = parse_x_interval(elem)
            if x:
                notes.append(x)
                continue
            s = parse_slope(elem)
            if s:
                notes.append(s)
    return notes


# ---------------------------------------------------------------------------
# Rule extraction
# ---------------------------------------------------------------------------

def extract_parameters(exprs):
    """Extract (parameter (key value)) expressions into a dict."""
    params = {}
    for expr in exprs:
        if is_list(expr) and len(expr) == 2 and expr[0] == 'parameter':
            inner = expr[1]
            if is_list(inner) and len(inner) == 2:
                key, val = inner
                # Try to convert numeric values
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        # Keep as string; convert boolean strings
                        if val == 'true':
                            val = True
                        elif val == 'false':
                            val = False
                params[key] = val
    return params


def extract_p_rules(exprs):
    """
    Extract P rules: (rule (P Y) ((BRICK ticks) (P ...)) weight)
                  or (rule (P Y) ((START count) (P ...)) weight)

    Returns two lists: brick_p_rules and start_p_rules.
    """
    brick_p = []
    start_p = []

    for expr in exprs:
        if not (is_list(expr) and len(expr) >= 3 and expr[0] == 'rule'):
            continue
        lhs = expr[1]
        if not (is_list(lhs) and len(lhs) == 2 and lhs[0] == 'P'):
            continue

        weight = float(expr[-1])
        rhs = expr[2]  # the body list

        if not is_list(rhs) or len(rhs) < 1:
            continue

        # The RHS is a list of symbols, first is BRICK/START, last is recursive P
        first = rhs[0]
        if is_list(first) and len(first) >= 2:
            sym = first[0]
            ticks = int(first[1])
            if sym == 'BRICK':
                brick_p.append({"sym": "BRICK", "ticks": ticks, "weight": weight})
            elif sym == 'START':
                # START count → ticks is in the recursive P subtraction
                # (P (- Y ticks)) — extract ticks from the second element
                p_sub = rhs[1]  # (P (- Y ticks))
                if is_list(p_sub) and len(p_sub) == 2 and is_list(p_sub[1]):
                    actual_ticks = int(p_sub[1][2])
                else:
                    actual_ticks = ticks * 480
                start_p.append({
                    "sym": "START",
                    "count": ticks,
                    "ticks": actual_ticks,
                    "weight": weight,
                })

    return brick_p, start_p


def extract_brick_rules(exprs):
    """
    Extract BRICK rules: (rule (BRICK ticks) (notes...) (builtin brick Name) weight)

    Returns dict: {ticks: {brick_name: [{"notes": [...], "weight": w}, ...]}}
    """
    bricks = {}

    for expr in exprs:
        if not (is_list(expr) and len(expr) >= 4 and expr[0] == 'rule'):
            continue
        lhs = expr[1]
        if not (is_list(lhs) and len(lhs) == 2 and lhs[0] == 'BRICK'):
            continue

        ticks = int(lhs[1])
        weight = float(expr[-1])

        # Find the brick name from (builtin brick Name)
        builtin_expr = expr[-2]
        if is_list(builtin_expr) and len(builtin_expr) == 3 and builtin_expr[0] == 'builtin':
            brick_name = builtin_expr[2]
        else:
            brick_name = "unknown"

        # The note body is expr[2] (the second element after 'rule')
        body = expr[2]
        if is_list(body):
            notes = parse_note_sequence(body)
        else:
            notes = []

        ticks_str = str(ticks)
        if ticks_str not in bricks:
            bricks[ticks_str] = {}
        if brick_name not in bricks[ticks_str]:
            bricks[ticks_str][brick_name] = []

        bricks[ticks_str][brick_name].append({"notes": notes, "weight": weight})

    return bricks


def extract_start_rules(exprs):
    """
    Extract START rules: (rule (START Z) ((ClusterX Z)) weight)

    Returns list of {"rhs": "Cluster0", "weight": 0.12}
    """
    rules = []
    for expr in exprs:
        if not (is_list(expr) and len(expr) >= 3 and expr[0] == 'rule'):
            continue
        lhs = expr[1]
        if not (is_list(lhs) and len(lhs) == 2 and lhs[0] == 'START'):
            continue

        weight = float(expr[-1])
        rhs = expr[2]

        # RHS is ((ClusterX Z)) — a list containing a single sublist
        if is_list(rhs) and len(rhs) >= 1:
            first = rhs[0]
            if is_list(first) and len(first) >= 1:
                cluster_name = first[0]
            elif is_atom(first):
                cluster_name = first
            else:
                continue
            rules.append({"rhs": cluster_name, "weight": weight})

    return rules


def extract_cluster_rules(exprs):
    """
    Extract Cluster transition rules:
        (rule (ClusterX Z) (Qn (ClusterY (- Z 1))) weight)

    Returns list of {"lhs": "Cluster0", "terminal": "Q0", "next": "Cluster0to1", "weight": 1.0}
    """
    rules = []
    for expr in exprs:
        if not (is_list(expr) and len(expr) >= 3 and expr[0] == 'rule'):
            continue
        lhs = expr[1]
        if not is_list(lhs):
            continue
        lhs_name = lhs[0]
        if not (isinstance(lhs_name, str) and lhs_name.startswith('Cluster')):
            continue

        weight = float(expr[-1])
        rhs = expr[2]

        # RHS is (Qn (ClusterY (- Z 1))) — a flat list
        if not is_list(rhs):
            continue

        terminal = None
        next_cluster = None

        for elem in rhs:
            if is_atom(elem) and elem.startswith('Q'):
                terminal = elem
            elif is_list(elem) and len(elem) >= 1:
                name = elem[0]
                if isinstance(name, str) and name.startswith('Cluster'):
                    next_cluster = name

        if terminal and next_cluster:
            rules.append({
                "lhs": lhs_name,
                "terminal": terminal,
                "next": next_cluster,
                "weight": weight,
            })

    return rules


def extract_q_rules(exprs):
    """
    Extract Q rules: (rule (Q0)(notes...) weight) or (rule (Q1)(notes...) weight)

    Returns dict: {"Q0": [{"notes": [...], "weight": w}], "Q1": [...]}
    """
    q_rules = {}

    for expr in exprs:
        if not (is_list(expr) and len(expr) >= 3 and expr[0] == 'rule'):
            continue
        lhs = expr[1]
        if not is_list(lhs):
            continue
        lhs_name = lhs[0] if lhs else None
        if not (isinstance(lhs_name, str) and lhs_name.startswith('Q')
                and lhs_name[1:].isdigit()):
            continue

        weight = float(expr[-1])
        body = expr[2]
        notes = parse_note_sequence(body) if is_list(body) else []

        if lhs_name not in q_rules:
            q_rules[lhs_name] = []
        q_rules[lhs_name].append({"notes": notes, "weight": weight})

    return q_rules


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def convert_grammar(grammar_path: str) -> dict:
    """
    Convert an Impro-Visor .grammar file to a structured dict.

    Args:
        grammar_path: Path to the .grammar file

    Returns:
        Dict ready for JSON serialization with keys:
        player, parameters, p_brick_rules, p_start_rules, start_rules,
        cluster_rules, q_rules, brick_rules
    """
    path = Path(grammar_path)
    exprs = parse_file(str(path))

    # Derive player name from filename
    player = path.stem

    parameters = extract_parameters(exprs)
    brick_p, start_p = extract_p_rules(exprs)
    brick_rules = extract_brick_rules(exprs)
    start_rules = extract_start_rules(exprs)
    cluster_rules = extract_cluster_rules(exprs)
    q_rules = extract_q_rules(exprs)

    return {
        "player": player,
        "parameters": parameters,
        "p_brick_rules": brick_p,
        "p_start_rules": start_p,
        "start_rules": start_rules,
        "cluster_rules": cluster_rules,
        "q_rules": q_rules,
        "brick_rules": brick_rules,
    }


def convert_and_save(grammar_path: str, output_path: str = None) -> str:
    """
    Convert a grammar and save as JSON.

    Args:
        grammar_path: Path to .grammar file
        output_path: Output JSON path (default: supercollider/grammars/<Player>.json)

    Returns:
        Path to the written JSON file.
    """
    data = convert_grammar(grammar_path)

    if output_path is None:
        from python.config import GRAMMARS_DIR
        GRAMMARS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = str(GRAMMARS_DIR / f"{data['player']}.json")

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse
    from python.config import SOURCE_GRAMMARS_DIR

    parser = argparse.ArgumentParser(
        description='Convert an Impro-Visor .grammar file to JSON.',
    )
    parser.add_argument('grammar', nargs='?', default='LesterYoung',
                        help='Player name (e.g. LesterYoung) or path to a .grammar file. '
                             'If a bare name, looks in data/grammars/. '
                             'Default: LesterYoung')
    parser.add_argument('-o', '--output', default=None,
                        help='Output JSON path (default: supercollider/grammars/<Player>.json)')
    args = parser.parse_args()

    grammar_path = args.grammar
    # If it doesn't look like a path, resolve as player name in data/grammars/
    if not grammar_path.endswith('.grammar') and '/' not in grammar_path:
        grammar_path = str(SOURCE_GRAMMARS_DIR / f"{grammar_path}.grammar")

    out = convert_and_save(grammar_path, args.output)

    # Print summary
    data = json.load(open(out))
    p = data['parameters']
    br = data['brick_rules']
    total_brick = sum(sum(len(v) for v in dur.values()) for dur in br.values())
    brick_types = set()
    for dur in br.values():
        brick_types.update(dur.keys())

    print(f"Converted: {args.grammar}")
    print(f"Output:    {out}")
    print(f"Player:    {data['player']}")
    print(f"Parameters: {len(p)}")
    print(f"P rules:   {len(data['p_brick_rules'])} brick + {len(data['p_start_rules'])} start")
    print(f"BRICK rules: {total_brick} across {len(brick_types)} types, {len(br)} duration buckets")
    print(f"START rules: {len(data['start_rules'])}")
    print(f"Cluster rules: {len(data['cluster_rules'])}")
    print(f"Q rules:   {sum(len(v) for v in data['q_rules'].values())} "
          f"({', '.join(f'{k}:{len(v)}' for k, v in data['q_rules'].items())})")
    print(f"Pitch range: {p.get('min-pitch', '?')}–{p.get('max-pitch', '?')}")
