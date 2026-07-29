#!/usr/bin/env python3
"""
Score a real matcher's output through the two falsification channels.

Inputs: LogMap 4.0 (July-2021 standalone) run on the lifted SATCAT vocabulary
vs SSAO, in MATCHER and LITE modes, plus LogMap's own discarded and
hard-discarded candidate pools (the high-recall lexical layer every matcher
builds before selection). Each candidate correspondence is scored on:

  Channel I  (intensional): is the SSAO target reachable by any disjointness
             axiom in SSAO's subsumption closure? If not, no reasoner can
             ever reject the mapping.
  Channel II (extensional): catalogue-native counter-instances under a small,
             documented evidence library. A rule fires only where the
             catalogue itself carries the discriminating field; mappings with
             no applicable rule are reported as 'no extensional test defined'
             rather than silently passed.

Evidence library (each rule names its justification):
  E1 non-entity targets (statuses, operators, roles): instances that carry
     orbital elements or launch dates are tracked physical objects, not
     qualities or agents. Witness = subject instances with orbital data.
  E2 natural-body targets (stellar/central/reference bodies): launched
     objects are artificial. Witness = subject instances with a launch date.
  E3 category swaps between object kinds (Payload / RocketBody / Debris
     targets): witness = subject instances whose catalogue OBJECT_TYPE
     differs from the target kind.
  E4 residency targets (Resident_Space_Object, any orbit class): witness =
     subject instances with a decay date.
  E5 Geostationary_Orbit target: witness = subject instances with
     inclination > 5 degrees.

Run:  .venv/bin/python systems/systems_eval.py   (writes systems/systems_results.json)
"""
import json
import os
import sys
from collections import defaultdict

from rdflib import Graph, RDF, RDFS, OWL, URIRef, Namespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
KG = Namespace("https://w3id.org/tesseract/space-kg/")

SSAO_LOCAL = lambda u: u.rsplit("/", 1)[-1].rsplit("#", 1)[-1]

NON_ENTITY_TARGETS = {"Operational_Status_of_Spacecraft", "Satellite_Operator",
                      "Space_Object_Role", "Operational"}
NATURAL_BODY_TARGETS = {"Stellar_Body", "Central_Body", "Reference_Body",
                        "Natural_Celestial_Body", "Planetary_Body", "Natural_Space_Object",
                        "Natural_Satellite"}
# Rocket_Body_Debris denotes spent stages (catalogue R/B); Rocket_Debris denotes
# debris of rocket ORIGIN, which SATCAT's DEB/R-B typing cannot discriminate, so
# it deliberately has NO extensional rule here.
KIND_TARGETS = {"Payload": "Payload", "Spacecraft_Payload": "Payload",
                "Rocket_Body_Debris": "RocketBody"}
RESIDENCY_TARGETS = {"Resident_Space_Object", "Orbital_Object", "Artificial_Space_Object"}


def load_candidates():
    files = {
        "matcher_final": "out_matcher/logmap2_mappings.txt",
        "lite": "out_lite/logmap-lite-mappings.txt",
        "discarded": "out_matcher/logmap_discarded_mappings.txt",
        "hard_discarded": "out_matcher/logmap_hard_discarded_mappings.txt",
    }
    cands = []
    seen = set()
    for pool, path in files.items():
        full = os.path.join(HERE, path)
        if not os.path.exists(full):
            continue
        for line in open(full):
            parts = line.strip().split("|")
            if len(parts) < 4 or not parts[0].startswith("http"):
                continue
            key = (parts[0], parts[1])
            if key in seen:
                # keep the highest-priority pool occurrence only
                continue
            seen.add(key)
            cands.append({"subject": parts[0], "target": parts[1],
                          "relation": parts[2], "confidence": float(parts[3]),
                          "pool": pool})
    return cands


def main() -> None:
    # SSAO reachability
    g = Graph()
    g.parse(os.path.join(ROOT, "ontology", "SSAO_Rovetto.owl"), format="turtle")
    classes = {c for c in g.subjects(RDF.type, OWL.Class) if isinstance(c, URIRef)}
    parents = defaultdict(set)
    for s, o in g.subject_objects(RDFS.subClassOf):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            parents[s].add(o)

    def ancestors(c):
        out, stack = {c}, [c]
        while stack:
            for p in parents.get(stack.pop(), ()):
                if p not in out:
                    out.add(p)
                    stack.append(p)
        return out

    declared = set()
    for s, o in g.subject_objects(OWL.disjointWith):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            declared.add(frozenset((s, o)))
    reachable = set()
    for pair in declared:
        a, b = tuple(pair)
        for c in classes:
            anc = ancestors(c)
            if a in anc or b in anc:
                reachable.add(c)

    inst = Graph()
    inst.parse(os.path.join(ROOT, "kg", "out", "instances.ttl"), format="turtle")

    def subjects_of(kg_class_uri):
        return set(inst.subjects(RDF.type, URIRef(kg_class_uri)))

    def has_orbital_data(s):
        return (s, KG.periodMin, None) in inst or (s, KG.perigeeKm, None) in inst

    def witness(cand):
        subj_local = cand["subject"].rsplit("/", 1)[-1]
        tgt = SSAO_LOCAL(cand["target"])
        subs = subjects_of(cand["subject"])
        if not subs:
            return None, "subject class has no instances"
        if tgt in NON_ENTITY_TARGETS:
            w = sum(1 for s in subs if has_orbital_data(s) or (s, KG.launchDate, None) in inst)
            return (w, len(subs)), "E1 non-entity target: tracked objects are not statuses/operators"
        if tgt in NATURAL_BODY_TARGETS:
            w = sum(1 for s in subs if (s, KG.launchDate, None) in inst)
            return (w, len(subs)), "E2 natural-body target: launched objects are artificial"
        if tgt in KIND_TARGETS:
            want = KIND_TARGETS[tgt]
            w = sum(1 for s in subs if (s, RDF.type, KG[want]) not in inst)
            return (w, len(subs)), f"E3 category swap: instances not of catalogue kind {want}"
        if tgt in RESIDENCY_TARGETS:
            w = sum(1 for s in subs if (s, KG.decayDate, None) in inst)
            return (w, len(subs)), "E4 residency target: decayed instances are not resident"
        if tgt == "Geostationary_Orbit":
            w = 0
            for s in subs:
                v = inst.value(s, KG.inclinationDeg)
                if v is not None and float(v) > 5:
                    w += 1
            return (w, len(subs)), "E5 geostationary target: inclination > 5 degrees"
        return None, "no extensional test defined"

    results = []
    for cand in load_candidates():
        tgt_uri = URIRef(cand["target"])
        intensional = tgt_uri in reachable
        w, rule = witness(cand)
        row = {**cand,
               "target_local": SSAO_LOCAL(cand["target"]),
               "intensionally_rejectable": intensional,
               "evidence_rule": rule}
        if w is not None:
            row["extensional_witnesses"], row["population"] = w
            row["witness_rate"] = round(w[0] / w[1], 4) if w[1] else None
        results.append(row)

    summary = {
        "candidates_total": len(results),
        "intensionally_rejectable": sum(1 for r in results if r["intensionally_rejectable"]),
        "with_extensional_test": sum(1 for r in results if "extensional_witnesses" in r),
        "extensionally_refuted_majority": sum(
            1 for r in results
            if r.get("witness_rate") is not None and r["witness_rate"] > 0.5),
        "logmap_conflicting_mappings_reported": 0,
    }
    out = {"summary": summary, "candidates": results}
    with open(os.path.join(HERE, "systems_results.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(summary, indent=2))
    for r in results:
        wr = r.get("witness_rate")
        ext = "n/a" if wr is None else "%d/%d (%.0f%%)" % (r["extensional_witnesses"], r["population"], 100 * wr)
        print("  [%14s] %28s -> %-34s conf=%.2f intens=%s ext=%s | %s" % (
            r["pool"], r["subject"].rsplit("/", 1)[-1], r["target_local"], r["confidence"],
            "YES" if r["intensionally_rejectable"] else "no", ext, r["evidence_rule"][:44]))


if __name__ == "__main__":
    main()
