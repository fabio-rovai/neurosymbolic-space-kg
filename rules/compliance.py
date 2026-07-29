#!/usr/bin/env python3
"""
Symbolic compliance rules over the space KG: debris-mitigation signals.

Rules, with their honest limits stated:

R1 (25-year signal, IADC lineage): the IADC space-debris mitigation guidelines'
   long-standing baseline limits post-mission LEO lifetime to 25 years (the
   FCC's 2024 US rule tightens to 5 years; ESA's Zero Debris approach targets
   the same direction). The catalogue records LAUNCH date, not end-of-mission
   date, so we compute a LOWER-BOUND signal: LEO objects, not decayed, whose
   status is non-operational (or debris/rocket bodies with any status) and
   whose launch is more than 25 years before the snapshot date. An object
   flagged by R1 has been in orbit for over 25 years in a non-mission state
   measured from launch, which UNDERSTATES nothing: mission time only adds to
   the true post-mission age... it OVERSTATES nothing either, since launch
   precedes mission end. It is a conservative floor on the population the
   25-year rule addresses.

R2 (decayed-yet-operational contradiction): catalogue rows carrying both a
   decay date and operational status '+'. Pure data-quality check; the target
   is the catalogue, not the objects.

R3 (graveyard compliance signal): GEO-band payloads, non-operational, still in
   the GEO band rather than the graveyard region: candidates for the
   super-synchronous disposal the guidelines prescribe.

Run:  .venv/bin/python rules/compliance.py    (writes rules/rules_results.json)
"""
import json
import os
from datetime import date

from rdflib import Graph, RDF, Namespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KG = Namespace("https://w3id.org/tesseract/space-kg/")
SNAPSHOT = date(2026, 7, 29)
RULE_YEARS = 25


def main() -> None:
    g = Graph()
    g.parse(os.path.join(ROOT, "kg", "out", "instances.ttl"), format="turtle")

    def has(s, cls):
        return (s, RDF.type, KG[cls]) in g

    def launch_year(s):
        v = g.value(s, KG.launchDate)
        try:
            return int(str(v)[:4])
        except (TypeError, ValueError):
            return None

    leo = set(g.subjects(RDF.type, KG.RegimeLEO))
    r1 = {"payload_nonop": 0, "rocket_bodies": 0, "debris": 0, "total": 0}
    for s in leo:
        if (s, KG.decayDate, None) in g:
            continue
        ly = launch_year(s)
        if ly is None or SNAPSHOT.year - ly <= RULE_YEARS:
            continue
        if has(s, "Payload") and (has(s, "StatusNonOperational") or has(s, "StatusUnknown")):
            r1["payload_nonop"] += 1
        elif has(s, "RocketBody"):
            r1["rocket_bodies"] += 1
        elif has(s, "Debris"):
            r1["debris"] += 1
        else:
            continue
        r1["total"] += 1

    r2 = 0
    for s in g.subjects(KG.decayDate, None):
        if has(s, "StatusOperational"):
            r2 += 1

    geo_band = set(g.subjects(RDF.type, KG.RegimeGEORegion)) | set(g.subjects(RDF.type, KG.RegimeGeostationaryCandidate))
    r3 = sum(1 for s in geo_band
             if has(s, "Payload") and has(s, "StatusNonOperational"))

    results = {
        "snapshot_date": SNAPSHOT.isoformat(),
        "rule_years": RULE_YEARS,
        "R1_leo_over25y_nonmission_lower_bound": r1,
        "R2_decayed_but_operational_rows": r2,
        "R3_geo_band_nonoperational_payloads_not_in_graveyard": r3,
        "leo_in_orbit_population": len([s for s in leo if (s, KG.decayDate, None) not in g]),
    }
    with open(os.path.join(HERE, "rules_results.json"), "w") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
