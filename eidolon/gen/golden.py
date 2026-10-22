"""The machine-generated golden set (`cases/generated/`): written by the generator, never by hand,
then verified INDEPENDENTLY (`eidolon validate`, `tests/gen/test_golden.py`).

    python -m eidolon.gen.golden
"""
from __future__ import annotations

from pathlib import Path

from .pipeline import generate, write_package

GOLDEN = (("study_party", 4), ("manor_wing", 4), ("study_party", 5), ("manor_wing", 6))
OUT = Path(__file__).resolve().parents[2] / "cases" / "generated"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for sk, seed in GOLDEN:
        r = generate(sk, seed)
        assert r.failed_at is None, (sk, seed, r.failed_at, r.problems)
        write_package(r, str(OUT / f"{sk}_s{seed}.json"))
        print(f"{sk}_s{seed}: murderer={r.package.solution.murderer} seal={r.package.seal[:16]} proof_core={r.report.proof['proof_core']}")


if __name__ == "__main__":
    main()
