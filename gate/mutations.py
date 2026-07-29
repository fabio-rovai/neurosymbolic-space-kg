#!/usr/bin/env python3
"""
Extensional falsification harness for candidate SATCAT-to-SSAO alignments.

The experiment, pre-stated:
1. INTENSIONAL channel: for each candidate mapping (including deliberately
   wrong but lexically plausible mutants), test whether ANY reasoning path in
   SSAO could reject it. Since rejection requires reaching a disjointness
   axiom, we compute the named-subsumption closure over SSAO's declared
   disjointness. SSAO declares exactly one disjoint pair
   (Cartesian_Ephemeris vs Keplerian_Ephemeris), so the expectation is that
   NO object-classification mutant is rejectable. The script verifies rather
   than assumes this.
2. EXTENSIONAL channel: each mutant mapping is tested against the 70k-object
   instance graph. A mutant is extensionally falsified if instances that the
   mapping would classify under the SSAO target provably violate the target's
   meaning USING ONLY catalogue-native evidence (status codes, decay dates,
   inclination), with the witness count reported.

A mapping that survives neither channel is refuted; a mapping the reasoner
cannot touch but the catalogue refutes in thousands of instances is the
paper's point.

Run:  .venv/bin/python gate/mutations.py    (writes gate/mutations_results.json)
"""
import json
import os
from collections import defaultdict

from rdflib import Graph, RDF, RDFS, OWL, URIRef, Namespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KG = Namespace("https://w3id.org/tesseract/space-kg/")

SSAO_TTL = os.path.join(ROOT, "ontology", "SSAO_Rovetto.owl")
INST_TTL = os.path.join(ROOT, "kg", "out", "instances.ttl")


def ssao_rejectability():
    """For every named SSAO class: can subsumption reach a disjointness axiom?"""
    g = Graph()
    g.parse(SSAO_TTL, format="turtle")
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
    disjoint_reachable = set()
    for pair in declared:
        a, b = tuple(pair)
        # any class subsumed by a is provably disjoint from any subsumed by b
        for c in classes:
            anc = ancestors(c)
            if a in anc or b in anc:
                disjoint_reachable.add(c)
    return g, classes, declared, disjoint_reachable, ancestors


MUTANTS = [
    {
        "id": "M1",
        "mapping": "kg:Payload -> ssao:Operational_Satellite (closeMatch)",
        "why_plausible": "Payloads are satellites and many are operational; a lexical or embedding matcher scores this pair highly.",
        "ssao_target": "Operational_Satellite",
        "witness_query": "payloads whose catalogue status is decayed or non-operational",
    },
    {
        "id": "M2",
        "mapping": "kg:RegimeGEORegion -> ssao:Geostationary_Orbit (closeMatch)",
        "why_plausible": "Geosynchronous and geostationary are conflated constantly; period matches exactly.",
        "ssao_target": "Geostationary_Orbit",
        "witness_query": "geosynchronous-band objects with inclination > 5 degrees",
    },
    {
        "id": "M3",
        "mapping": "kg:RocketBody -> ssao:Payload (closeMatch)",
        "why_plausible": "Both are launched objects with owner, launch date and orbit; schema-level features are near-identical.",
        "ssao_target": "Payload",
        "witness_query": "all rocket bodies (category swap: none carries a mission)",
    },
    {
        "id": "M4",
        "mapping": "kg:StatusDecayed -> ssao:Resident_Space_Object (broadMatch)",
        "why_plausible": "Every other catalogue class maps under Resident_Space_Object, so a matcher generalises the pattern.",
        "ssao_target": "Resident_Space_Object",
        "witness_query": "objects with a decay date (no longer resident)",
    },
]


def main() -> None:
    g, classes, declared, rejectable, _ = ssao_rejectability()
    local = {str(c).rsplit("/", 1)[-1].rsplit("#", 1)[-1]: c for c in classes}

    inst = Graph()
    inst.parse(INST_TTL, format="turtle")

    def count(cls=None, status=None, pred=None, test=None, require_no_decay=False):
        n = 0
        subjects = set(inst.subjects(RDF.type, KG[cls])) if cls else set(inst.subjects(RDF.type, KG[status]))
        for s in subjects:
            if status and cls and (s, RDF.type, KG[status]) not in inst:
                continue
            if require_no_decay and (s, KG.decayDate, None) in inst:
                continue
            if pred and test:
                vals = list(inst.objects(s, KG[pred]))
                if not vals or not test(float(vals[0])):
                    continue
            n += 1
        return n

    results = {
        "ssao": {
            "classes": len(classes),
            "declared_disjoint_pairs": len(declared),
            "declared_pairs_named": [
                sorted(str(x).rsplit("/", 1)[-1] for x in pair) for pair in declared
            ],
            "classes_reachable_by_any_disjointness": len(rejectable),
            "classes_unreachable_by_any_disjointness": len(classes) - len(rejectable),
        },
        "mutants": [],
    }

    payload_total = len(set(inst.subjects(RDF.type, KG.Payload)))
    for m in MUTANTS:
        target = local.get(m["ssao_target"])
        intensionally_rejectable = target in rejectable if target else None
        if m["id"] == "M1":
            witnesses = count(cls="Payload", status="StatusDecayed") + \
                count(cls="Payload", status="StatusNonOperational")
            population = payload_total
        elif m["id"] == "M2":
            witnesses = count(cls="RegimeGEORegion", pred="inclinationDeg", test=lambda v: v > 5)
            population = len(set(inst.subjects(RDF.type, KG.RegimeGEORegion)))
        elif m["id"] == "M3":
            witnesses = len(set(inst.subjects(RDF.type, KG.RocketBody)))
            population = witnesses
        else:  # M4
            witnesses = len(set(inst.subjects(RDF.type, KG.StatusDecayed)))
            population = witnesses
        results["mutants"].append({
            **m,
            "intensionally_rejectable_via_ssao_disjointness": intensionally_rejectable,
            "extensional_witnesses": witnesses,
            "population": population,
            "witness_rate": round(witnesses / population, 4) if population else None,
        })

    out = os.path.join(HERE, "mutations_results.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
