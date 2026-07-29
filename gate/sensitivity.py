#!/usr/bin/env python3
"""
Threshold sensitivity of the extensional channel.

Every derived orbit regime rests on a convention (2000 km for LEO, the
1400-1500 minute geosynchronous band, 5 degrees for a geostationary
candidate). A referee is entitled to ask whether the headline witness rates
are artefacts of those choices. This script re-derives the two
threshold-dependent mutants across a grid and reports the rates, so the
conventions can be moved and the conclusion checked rather than trusted.

M2 (geosynchronous band mapped to Geostationary_Orbit): swept over the
inclination cut-off that separates a geostationary candidate from an
inclined band resident, and over the period half-width that defines the
band itself.

M1 (payload mapped to Operational_Satellite): swept over the status
interpretation, since the choice of which catalogue status codes count as
non-mission is also a convention.

Run:  .venv/bin/python gate/sensitivity.py   (writes gate/sensitivity_results.json)
"""
import json
import os

from rdflib import Graph, RDF, Namespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KG = Namespace("https://w3id.org/tesseract/space-kg/")

INCLINATION_CUTOFFS = [1.0, 3.0, 5.0, 7.0, 10.0, 15.0]
BAND_HALFWIDTHS = [25, 50, 75, 100]   # minutes either side of 1436 (sidereal day)
SIDEREAL_MIN = 1436.0


def main() -> None:
    g = Graph()
    g.parse(os.path.join(ROOT, "kg", "out", "instances.ttl"), format="turtle")

    # collect in-orbit objects with period + inclination, independent of the
    # regime typing in the graph, so the sweep is not circular
    objs = []
    for s in set(g.subjects(RDF.type, KG.Payload)) | set(g.subjects(RDF.type, KG.RocketBody)) \
            | set(g.subjects(RDF.type, KG.Debris)) | set(g.subjects(RDF.type, KG.Unknown)):
        if (s, KG.decayDate, None) in g:
            continue
        p = g.value(s, KG.periodMin)
        i = g.value(s, KG.inclinationDeg)
        per = g.value(s, KG.perigeeKm)
        if p is None or i is None:
            continue
        objs.append((float(p), float(i), float(per) if per is not None else None))

    results = {"objects_with_period_and_inclination": len(objs), "M2_sweep": [], "M1_sweep": []}

    for hw in BAND_HALFWIDTHS:
        band = [(p, i, per) for (p, i, per) in objs
                if abs(p - SIDEREAL_MIN) <= hw and (per is None or per <= 36500)]
        for cut in INCLINATION_CUTOFFS:
            inclined = sum(1 for (_, i, _) in band if i > cut)
            results["M2_sweep"].append({
                "band_halfwidth_min": hw,
                "inclination_cutoff_deg": cut,
                "band_population": len(band),
                "witnesses_inclined": inclined,
                "witness_rate": round(inclined / len(band), 4) if band else None,
            })

    # M1: which status codes count as non-mission
    payloads = set(g.subjects(RDF.type, KG.Payload))
    def count(status_classes, include_decayed):
        n = 0
        for s in payloads:
            if include_decayed and (s, KG.decayDate, None) in g:
                n += 1
                continue
            if any((s, RDF.type, KG[c]) in g for c in status_classes):
                n += 1
        return n
    variants = [
        ("decayed only", [], True),
        ("decayed + non-operational (paper)", ["StatusNonOperational"], True),
        ("decayed + non-op + unknown", ["StatusNonOperational", "StatusUnknown"], True),
        ("non-operational only, in orbit", ["StatusNonOperational"], False),
    ]
    for label, classes, dec in variants:
        w = count(classes, dec)
        results["M1_sweep"].append({
            "definition": label, "witnesses": w, "population": len(payloads),
            "witness_rate": round(w / len(payloads), 4),
        })

    with open(os.path.join(HERE, "sensitivity_results.json"), "w") as f:
        json.dump(results, f, indent=2)

    print(f"objects with period+inclination (in orbit): {len(objs)}")
    print("\nM2: geosynchronous band -> Geostationary_Orbit")
    print(f"{'band +/- min':>13}{'incl cutoff':>13}{'band pop':>10}{'witnesses':>11}{'rate':>9}")
    for r in results["M2_sweep"]:
        print(f"{r['band_halfwidth_min']:>13}{r['inclination_cutoff_deg']:>13}"
              f"{r['band_population']:>10}{r['witnesses_inclined']:>11}"
              f"{100 * (r['witness_rate'] or 0):>8.1f}%")
    print("\nM1: payload -> Operational_Satellite, by non-mission definition")
    for r in results["M1_sweep"]:
        print(f"  {r['definition']:<38} {r['witnesses']:>6}/{r['population']} "
              f"({100 * r['witness_rate']:.1f}%)")


if __name__ == "__main__":
    main()
