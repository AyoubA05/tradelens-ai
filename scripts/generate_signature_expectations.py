"""Write the signing expectations the TypeScript suite asserts against.

The HMAC scheme exists in Python and TypeScript and neither can import the
other, so `docs/contracts/service-signature-vectors.json` holds the inputs and
this script derives the outputs from the Python implementation. The TypeScript
suite then asserts it reproduces them exactly.

Run after any change to the signing scheme. CI regenerates and diffs, so a
change on one side that is not mirrored on the other fails the build rather
than failing in production.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.tradelens.api.security import sign_request  # noqa: E402

VECTORS = pathlib.Path("docs/contracts/service-signature-vectors.json")
DEST = pathlib.Path("web/__tests__/fixtures/signature-expectations.json")


def main() -> None:
    spec = json.loads(VECTORS.read_text(encoding="utf-8"))
    out = {
        v["name"]: sign_request(
            spec["secret"],
            v["timestamp"],
            v["method"],
            v["path"],
            v["query"],
            v["body"].encode("utf-8"),
        )
        for v in spec["vectors"]
    }
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(out)} expectations to {DEST}")


if __name__ == "__main__":
    main()
