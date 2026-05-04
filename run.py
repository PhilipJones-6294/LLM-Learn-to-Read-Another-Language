#!/usr/bin/env python3
"""
Top-level launcher — run from the project root:

    python run.py
    python run.py --chapter 1
    python run.py --input data/input/book.txt --output data/output/gradient.txt
    python run.py --force-preprocess
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cognitive_gradient.main import _parse_args, run

args = _parse_args()
run(
    force_preprocess=args.force_preprocess,
    chapter_filter=args.chapter,
    input_path=args.input,
    output_path=args.output,
)
