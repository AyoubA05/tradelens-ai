"""Generate a differential corpus for the canonical-query implementations.

The query canonicaliser exists twice — `src/tradelens/api/security.py` and
`web/lib/api/sign.ts` — and a disagreement between them is an authentication
outage that only appears in production, on whichever query shape nobody thought
to test. Hand-written vectors cover the cases someone imagined; this covers the
cases they did not.

Python is the reference: it derives the expected canonical form for every case,
and the TypeScript suite asserts it reproduces each one.
"""

import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.tradelens.api.security import canonical_query  # noqa: E402

DEST = pathlib.Path("web/__tests__/fixtures/canonical-query-cases.json")

# Characters chosen to probe the places the two languages encode differently:
# the sub-delims JavaScript leaves bare, the space/plus ambiguity, reserved
# delimiters, non-ASCII, and percent signs that are already escapes.
# Alphanumerics span the full ranges, not a sparse sample: a review noted the
# earlier subset (a,b,c / A,Z / 0,9) could miss an encoder that treated some
# other letter or digit specially.
ALPHABET = list(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "-._~!*'()&=+%; ,/?:@$#[]{}\"\\<>|^`é中🙂\t\n"
)

HANDWRITTEN = [
    "",
    "a=1",
    "a=1&b=2",
    "b=2&a=1",
    "a=1&a=2",
    "a=2&a=1",
    "debug",
    "debug=",
    "a",
    "=1",
    "=",
    "&",
    "&&",
    "a=1&&b=2",
    "s=a+b",
    "s=a%20b",
    "s=a b",
    "q=a!b'c(d)e*f",
    "note=caf%C3%A9",
    "note=café",
    "e=100%25",
    "u=%2Fpath%2Fto",
    "z=&y=",
    "k=v&k=v",
    "emoji=🙂",
    "tab=a%09b",
    "semi=a;b",
    "comma=a,b",
    "eq=a=b",
    "amp=a%26b",
    # Leading "?" is literal data because the input is already a raw query and
    # excludes the URL delimiter. URLSearchParams strips one unless the
    # TypeScript canonicaliser protects it before parsing.
    "?a=1",
    "?a=1&b=2",
    "?",
    # Malformed percent-escapes. Python's unquote is lenient and the WHATWG
    # parser substitutes U+FFFD, so a review flagged this as a plausible
    # remaining disagreement surface. Verified equivalent on both sides and
    # pinned here so it stays that way — the hypothesis was reasonable even
    # though the answer was no.
    "x=%zz",
    "x=%2",
    "x=%",
    "x=100%",
    "a=%GG&b=1",
    "%=1",
    "x=%%41",
    "x=%41",
    # Truncated multi-byte UTF-8 sequences: both sides must land on U+FFFD.
    "x=%e4%b8",
    "x=%C3%28",
    "x=%FF",
    "x=%C3",
]


def _random_case(rng: random.Random) -> str:
    parts = []
    for _ in range(rng.randint(1, 4)):
        name = "".join(rng.choice(ALPHABET) for _ in range(rng.randint(1, 6)))
        if rng.random() < 0.2:
            parts.append(name)
        else:
            value = "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 8)))
            parts.append(f"{name}={value}")
    return "&".join(parts)


def main() -> None:
    rng = random.Random(20260818)  # fixed seed: the corpus must be reproducible
    cases = list(HANDWRITTEN)
    seen = set(cases)
    while len(cases) < 400:
        case = _random_case(rng)
        if case not in seen:
            seen.add(case)
            cases.append(case)

    out = [{"query": c, "canonical": canonical_query(c)} for c in cases]
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(out)} canonical-query cases to {DEST}")


if __name__ == "__main__":
    main()
