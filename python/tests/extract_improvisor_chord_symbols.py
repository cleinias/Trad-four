import os
import warnings
from python.leadsheet.parser import parse
from python.config import LEADSHEETS_DIR

LS_DIR = str(LEADSHEETS_DIR)

all_symbols = set()
for fname in os.listdir(LS_DIR):
    if not fname.endswith('.ls'):
        continue
    with warnings.catch_warnings(record=True):
        warnings.simplefilter('always')
        ls = parse(os.path.join(LS_DIR, fname))
    for event in ls.chord_timeline:
        all_symbols.add(event.symbol)

with open('chord_symbols.txt', 'w') as f:
    for sym in sorted(all_symbols):
        f.write(sym + '\n')

print(f"Saved {len(all_symbols)} unique chord symbols to chord_symbols.txt")