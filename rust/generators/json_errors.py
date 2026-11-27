"""Write the `json.loads` error vectors `rust/hokace/core/tests/json_errors.rs` checks
`pyjson::decode_error` against.

The PC engine reads its receipts and the launcher list with ``json.loads``, and a document it
refuses surfaces as ``JSONDecodeError: <message>: line L column C (char P)``. Each line of the
output is ``[text, message]``, ``message`` ``null`` where this Python (3.12) accepts the text:
hand-written edge cases (strings, escapes, surrogates, numbers, literals, whitespace, a BOM) and a
seeded sample of truncations, deletions, replacements and insertions of a receipt and a launcher
list.

    .venv\\Scripts\\python.exe rust\\generators\\json_errors.py [--check]

``--check`` fails when the committed vectors are stale.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

OUTPUT = pathlib.Path(__file__).resolve().parents[1] / "hokace" / "core" / "tests" / "json_errors.jsonl"

HANDWRITTEN = [
    "", " ", "\n\n", "{", "}", "[", "]", "{}", "[]", "{ }", "[ ]", "{\"a\"}", "{\"a\":}", "{\"a\" 1}",
    "{\"a\":1,}", "[1,]", "[1 2]", "{\"a\":1 \"b\":2}", "{1:2}", "{'a':1}", "nul", "null", "nulls", "tru",
    "true", "fals", "false", "NaN", "Na", "Infinity", "Infinit", "-Infinity", "-Infinit", "-", "--1", "-0",
    "01", "1.", "1.e5", "1.5", "1e", "1e+", "1e-5", "1E5", ".5", "+1", "1x", "[1e]", "[1.]", "[-]", "\"",
    "\"abc", "\"a\\", "\"a\\\"", "\"\\q\"", "\"\\u12\"", "\"\\u12", "\"\\u1234", "\"\\u1234\"", "\"\\uzzzz\"",
    "\"\\ud800\"", "\"\\ud800\\udc00\"", "\"\\ud800\\u12\"", "\"\\ud800\\uzzzz\"", "\"\\ud800\\u0041\"",
    "\"\\ud800\\", "\"\\ud800\\x\"", "\"a\x01b\"", "\"tab\there\"", "\"new\nline\"", "\"\x7f\"",
    "\ufeff{}", "{}\ufeff", "[1]\n x", "[1]  ", "  [1]", "\t{\"a\":\t1}\r\n", "{\"a\":[1,{\"b\":}]}",
    "[\"\u5b57\u4f53\", x]", "\"\u5b57\", 1", "{\"a\":1}}", "[[[]]", "[[]]]", "{\"a\":{\"b\":{}}",
]


def corpus() -> list[str]:
    receipt = json.dumps({"schema": 1, "state": "complete", "action": "install", "files": [
        {"relative": "WXQ_Data\\Package\\builtin\\7\\7_0.db", "before": "ab" * 32, "after": "cd" * 32},
        {"relative": "LocalFileList.json", "before": None, "after": "ef" * 32}]}, indent=2)
    launcher = json.dumps([{"file": "WXQ_Data\\Package\\builtin\\7\\7.db", "file_size": 4560},
                           {"file": "Data\\\u5b57\u4f53\\font.ttf", "file_size": -1.5e3}],
                          ensure_ascii=False, separators=(", ", ": "))
    rng = random.Random(20261127)
    alphabet = ['"', "\\", ",", ":", "}", "]", "{", "[", "x", "\x01", "\n", "-", "0", "e", "u", " ", "."]
    texts = list(HANDWRITTEN)
    for base in (receipt, launcher):
        texts += [base[:i] for i in range(0, len(base), 3)]
        for _ in range(400):
            i = rng.randrange(len(base))
            texts.append(base[:i] + base[i + 1:])
            texts.append(base[:i] + rng.choice(alphabet) + base[i + 1:])
            texts.append(base[:i] + rng.choice(alphabet) + base[i:])
    seen, unique = set(), []
    for text in texts:
        if text not in seen:
            seen.add(text)
            unique.append(text)
    return unique


def render() -> str:
    lines = []
    for text in corpus():
        try:
            json.loads(text)
            message = None
        except json.JSONDecodeError as exc:
            message = str(exc)
        lines.append(json.dumps([text, message], ensure_ascii=True))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when the committed vectors are stale")
    args = parser.parse_args()
    text = render()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != text:
            print(f"{OUTPUT} is stale; re-run without --check", file=sys.stderr)
            return 1
        print(f"{OUTPUT} is current")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT} ({text.count(chr(10))} vectors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
