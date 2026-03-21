"""
config.py — Trad-Four
Centralized path constants for data files.

Uses Path(__file__).resolve() so paths work from any working directory.
"""

from pathlib import Path

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
DATA_DIR       = PROJECT_ROOT / 'data'
VOCAB_DIR      = DATA_DIR / 'vocab'
LEADSHEETS_DIR = DATA_DIR / 'leadsheets'
DICT_PATH      = VOCAB_DIR / 'My.dictionary'
SUB_PATH       = VOCAB_DIR / 'My.substitutions'
