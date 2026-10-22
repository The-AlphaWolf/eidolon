"""`CasePackage` (§1.2, §18.1): the sealed output of generation and the ONLY input of the solver.

The solver never sees the planner. It sees a `Case` (the CaseLog), an evidence table, the
secrets, and — for comparison only — the `CanonicalSolution` the generator claims. Everything
the generator *declares* (`structure`, `solution.alternatives`, `Evidence.load_bearing`) is
metadata to be CONFIRMED (I-43), never read as a premise: `solve()` takes no `solution` argument
and `tests/solve/test_independence.py` proves that scrambling every declared field leaves the
survivor set byte-identical.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..decision.secrets import Secret
from ..evidence.model import Evidence
from ..world.case import Case
from ..world.ids import ActorId, EventId, EvidenceId, LocationId, ObjectId
from ..world.propositions import Interval

ARCHITECTURE_VERSION = "0.4"
GENERATOR_VERSION = "6.0"

# Constants the solver AND the independent verifier both read. They live here, with the sealed
# package, so the verifier imports nothing from `solver`/`lattice` — not even a number (ADR-28, N-13).
BIN = 10            # width of a time bin: "exactly one (murderer, method, time_bin)"
MAX_WINDOW = 40     # widest murder window resolved tick by tick; a wider one is REJECTED, never approximated


class MethodSpec(BaseModel):
    """§18.2 `MethodSpec`. `admits` names the non-murder candidate classes the method allows
    (`Accident`, `Suicide`); each one declared here becomes a candidate the solver must
    exclude with reachable material (§19.5). Both v1 skeletons are blunt-force and admit none."""
    model_config = ConfigDict(frozen=True)

    kind: str
    weapon: ObjectId
    admits: tuple[Literal["Accident", "Suicide"], ...] = ()


class EliminationStructure(BaseModel):
    """§18.2 (I-43): DECLARED by the skeleton, REALISED by the planner, CONFIRMED by V-5."""
    model_config = ConfigDict(frozen=True)

    alibi_window: int
    corroborator_rule: Literal["outside_component"] = "outside_component"
    time_pin: Literal["physical", "witness_L2"] = "physical"
    containment: Literal["device_L3"] = "device_L3"   # `watcher_L2` needs a NoStranger perception
    # derivation the Phase 1 model does not have (`world/perception.py` emits `NotAt` per known
    # actor only) — recorded as a Phase 6 scope limit, not offered by either v1 skeleton.
    secret_clearance: int
    opportunity_pin: bool


class TimeShift(BaseModel):
    """One IN-FORCE memory distortion (§8.7, stage 9): the witness `actor` recalls everything
    grounded in memory `memory` shifted by `delta` minutes until the player corrects it. Chosen
    by the generator from what `minds.memory.encode_memories` would assign, bounded per witness;
    `know_ids` are the testimony atoms (`S:P…`) the memory covers."""
    model_config = ConfigDict(frozen=True)

    memory: str
    actor: ActorId
    delta: int
    know_ids: tuple[str, ...]


class MemoryBoost(BaseModel):
    """§19.4 (I-39): "generation raises that memory's `strength_0` until [an expressible query
    reaches `strong`]". `minds.memory.encode_memories` seals `strength_0` from salience and decay
    alone, so the raise is recorded HERE, against the memory id it derives; the session loader
    applies it (Phase 7/8) and V-4 checks retrievability with it applied. A boosted memory is
    >= 0.6 strong, hence distortion-free (§8.7)."""
    model_config = ConfigDict(frozen=True)

    memory: str
    actor: ActorId
    strength_bp: int


class Alternative(BaseModel):
    """What the GENERATOR says excludes one non-solution candidate. Declared, never trusted."""
    model_config = ConfigDict(frozen=True)

    candidate: str            # ActorId | "Outsider"
    reason: Literal["alibi", "physical", "containment"]
    material: tuple[str, ...] = ()


class CanonicalSolution(BaseModel):
    """§1.2 `solution`: enough structure for proof and alternate-hypothesis analysis —
    murderer, event, place, moment, method/weapon, opportunity, the load-bearing items, the
    critical constraints and one declared exclusion per alternative."""
    model_config = ConfigDict(frozen=True)

    murderer: ActorId
    victim: ActorId
    method: str
    weapon: ObjectId
    location: LocationId
    interval: Interval
    murder_event: EventId
    motive_kind: str
    approach: Interval                       # the murderer's stay in the murder room (opportunity)
    opportunity_witness: ActorId | None = None
    load_bearing: tuple[EvidenceId, ...] = ()
    critical_constraints: tuple[str, ...] = ()
    alternatives: tuple[Alternative, ...] = ()


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class CasePackage(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    id: str
    skeleton_id: str
    seed: int
    generator_version: str = GENERATOR_VERSION
    architecture_version: str = ARCHITECTURE_VERSION
    case: Case
    evidence: tuple[Evidence, ...]
    secrets: tuple[Secret, ...]
    accounts: tuple[str, ...] = ()
    """ADR-23: the ACCOUNT TOKENS (`"<event>@<actor>"`, `minds.accounts`) the case's covers and breakers rely on.
    The package DECLARES them and does not script them: an account's content is derived from the speaker's own
    `Participated` knowledge (never sealed as a second copy), and nothing is pre-loaded into a session — a token
    enters play only by being heard (I-50). The solver never reads this field; its testimony comes from
    `derive_perception`, so a package with the declaration scrambled or removed yields the same verdict."""
    method: MethodSpec
    structure: EliminationStructure
    solution: CanonicalSolution
    distortions: tuple[TimeShift, ...] = ()
    memory_boosts: tuple[MemoryBoost, ...] = ()
    difficulty: str = "standard"
    fairness_level: int = 2
    """§19.5: 2 = `standard` (L3 ∪ L2), 3 = `hard-fair`. Sealed WITH the package so the verifier reads the
    level the case was built for, never the one a proof asserts about itself (ADR-28, H4)."""
    seal: str = ""

    def content_hash(self) -> str:
        """The seal (§18.3 stage 11): sha256 over a canonical rendering. Unordered tuple
        fields are sorted by their own canonical JSON so two packages with equal content hash
        equally whatever order they were built in (same rule as `Case.content_hash`, I-4)."""
        payload = self.model_dump(mode="json", exclude={"seal", "case"})
        payload["case"] = self.case.content_hash()
        for f in ("evidence", "secrets", "accounts"):
            payload[f] = sorted(payload[f], key=canonical_json)
        return hashlib.sha256(canonical_json(payload).encode()).hexdigest()

    def sealed(self) -> "CasePackage":
        return self.model_copy(update={"seal": self.content_hash()})

    def verify_seal(self) -> bool:
        return bool(self.seal) and self.seal == self.content_hash()


# ------------------------------------------------------------------ the sealed bundle (ADR-29, I-58)
class SealRefusal(ValueError):
    """A sealed case that must not be loaded: a seal does not match, or its proof does not verify."""


def _sha(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def bundle_seal(package_seal: str, proof: dict, report: dict) -> str:
    return _sha({"package": package_seal, "proof": _sha(proof), "report": _sha(report)})


class SealedCase(BaseModel):
    """A case is persisted as ONE bundle `{package, proof, report, bundle_seal}` — the proof is never a
    detached file next to the package (H10). `bundle_seal` binds the three together, so editing or
    swapping any one of them is detected before anyone replays the proof."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    package: CasePackage
    proof: dict
    report: dict
    bundle_seal: str

    @classmethod
    def seal(cls, package: CasePackage, proof: dict, report: dict) -> "SealedCase":
        return cls(package=package, proof=proof, report=report,
                   bundle_seal=bundle_seal(package.seal, proof, report))


REQUIRED_STAGES = ("V-0", "V-1", "V-2", "V-3", "V-4", "V-5", "V-6", "V-7")


def load_sealed_case(path: str) -> SealedCase:
    """The ONLY reader (I-58). Refuses unless every seal matches, `verify_proof(package, proof) == []`,
    and the report records every stage OK at FULL scale. Raises `SealRefusal`, never anything else."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except Exception as e:                                           # noqa: BLE001
        raise SealRefusal(f"unreadable bundle: {type(e).__name__}") from e
    return load_sealed_text(text)


def load_sealed_text(text: str) -> SealedCase:
    """`load_sealed_case`'s body, for a bundle that is embedded in a save (Phase 7) rather than a file. Same checks, same
    refusal type — there is exactly one verifier (I-58), this is just where it reads from."""
    import json

    from .proof import verify_proof
    try:
        doc = json.loads(text)
        if not isinstance(doc, dict) or set(doc) != {"package", "proof", "report", "bundle_seal"}:
            raise SealRefusal("not a sealed-case bundle")
        case = SealedCase(package=CasePackage.model_validate(doc["package"]), proof=doc["proof"],
                          report=doc["report"], bundle_seal=doc["bundle_seal"])
    except SealRefusal:
        raise
    except Exception as e:                                           # noqa: BLE001
        raise SealRefusal(f"unreadable bundle: {type(e).__name__}") from e
    pkg = case.package
    if not pkg.verify_seal():
        raise SealRefusal("package seal does not verify")
    if not isinstance(case.proof, dict) or case.proof.get("package_seal") != pkg.seal:
        raise SealRefusal("proof is about a different package")
    if case.bundle_seal != bundle_seal(pkg.seal, case.proof, case.report):
        raise SealRefusal("bundle seal does not verify")
    if bad := verify_proof(pkg, case.proof):
        raise SealRefusal(f"proof does not verify: {bad[0]}")
    # I-43/I-58: `solution` is metadata to be CONFIRMED. `verify_proof` never reads it (independence), so the one place
    # the declared murderer, place and moment meet the verified ones is here — a scored fact is the PROVEN one.
    sol, proof = pkg.solution, case.proof
    if proof.get("unique") is not True or proof.get("survivors") != [sol.murderer]:
        raise SealRefusal(f"declared murderer {sol.murderer!r} is not the proof's unique survivor {proof.get('survivors')!r}")
    if proof.get("murder_loc") != sol.location or list(proof.get("window", ())) != list(sol.interval):
        raise SealRefusal("declared murder place/moment disagree with the proof's")
    rep = case.report
    stages = rep.get("stages", {}) if isinstance(rep, dict) else {}
    if not (isinstance(rep, dict) and rep.get("ok") is True and rep.get("package") == pkg.id
            and all(isinstance(stages.get(s), dict) and stages[s].get("ok") is True for s in REQUIRED_STAGES)):
        raise SealRefusal("report does not record every stage OK")
    if stages["V-7"].get("scale") != "full":
        raise SealRefusal(f"V-7 ran at scale {stages['V-7'].get('scale')!r}, not the architecture's full scale")
    return case
