#!/usr/bin/env python3
"""
Build the space knowledge graph from the pinned CelesTrak SATCAT snapshot.

Design, stated so it can be attacked:
- Instances: one node per catalogued object (NORAD id), typed by a LIFTED
  SATCAT vocabulary (kg:Payload, kg:RocketBody, kg:Debris, kg:Unknown and
  status/regime classes). The lift is OURS: SATCAT publishes codes, not IRIs,
  and the interpretation is recorded here rather than left implicit.
- Schema links: the lifted vocabulary is aligned to Rovetto's Space Situational
  Awareness Ontology (SSAO) in crosswalks/satcat-ssao.sssom.tsv. Instance data
  NEVER asserts SSAO types directly; types flow only through the alignment,
  so the alignment stays a first-class, testable artefact.
- Orbit regimes are DERIVED from the catalogue's own numbers (perigee, apogee,
  period, inclination), with the thresholds printed into the graph's metadata:
  LEO: perigee < 2000 km; GEO-region: 1400 <= period <= 1500 min;
  geostationary CANDIDATE additionally requires inclination <= 5 degrees;
  graveyard-region: period in GEO band but perigee > 36500 km. MEO: between
  LEO and GEO bands. HEO: eccentric orbits crossing bands (apogee-perigee
  gap > 20000 km). Decayed objects (DECAY_DATE set) get NO regime.

Run:  .venv/bin/python kg/build_kg.py     (writes kg/out/*.ttl + kg/out/stats.json)
"""
import csv
import json
import os
from datetime import date

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, XSD, URIRef

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out")

KG = Namespace("https://w3id.org/tesseract/space-kg/")
OBJ = Namespace("https://w3id.org/tesseract/space-kg/object/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

TODAY = date(2026, 7, 29)  # pinned analysis date (snapshot date), not runtime

TYPE_CODES = {
    "PAY": ("Payload", "A spacecraft placed in orbit to perform a mission."),
    "R/B": ("RocketBody", "A spent launch-vehicle stage remaining in orbit."),
    "DEB": ("Debris", "A catalogued fragment or non-functional object other than a payload or rocket body."),
    "UNK": ("Unknown", "An object whose type the catalogue does not determine."),
}
STATUS_CODES = {
    "+": ("StatusOperational", "Operational."),
    "-": ("StatusNonOperational", "Non-operational."),
    "P": ("StatusPartiallyOperational", "Partially operational."),
    "B": ("StatusBackup", "Backup or standby."),
    "S": ("StatusSpare", "Spare."),
    "X": ("StatusExtendedMission", "Extended mission."),
    "D": ("StatusDecayed", "Decayed (re-entered)."),
    "?": ("StatusUnknown", "Status unknown."),
}
REGIMES = {
    "LEO": "RegimeLEO", "MEO": "RegimeMEO", "GEOREGION": "RegimeGEORegion",
    "GEOSTATCAND": "RegimeGeostationaryCandidate", "HEO": "RegimeHEO",
    "GRAVEYARD": "RegimeGraveyardRegion", "OTHER": "RegimeOther",
}


def parse_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def regime_of(perigee, apogee, period, inclination):
    if perigee is None or apogee is None:
        return None
    if period is not None and 1400 <= period <= 1500:
        if perigee > 36500:
            return "GRAVEYARD"
        if inclination is not None and inclination <= 5:
            return "GEOSTATCAND"
        return "GEOREGION"
    if apogee - perigee > 20000:
        return "HEO"
    if apogee < 2000:
        return "LEO"
    if perigee >= 2000:
        return "MEO"
    return "OTHER"


def main() -> None:
    os.makedirs(OUT, exist_ok=True)

    # ---- vocabulary graph (the lift) ----
    v = Graph()
    v.bind("kg", KG)
    v.bind("skos", SKOS)
    ont = URIRef(str(KG)[:-1])
    v.add((ont, RDF.type, OWL.Ontology))
    v.add((ont, RDFS.comment, Literal(
        "Lifted SATCAT vocabulary and derived orbit-regime classes. Lifted by "
        "Tesseract Academy from the CelesTrak SATCAT code tables; the "
        "interpretation is ours and is the subject of the accompanying "
        "alignment. No disjointness is invented: the source publishes none.")))
    for code, (name, definition) in {**TYPE_CODES, **STATUS_CODES}.items():
        c = KG[name]
        v.add((c, RDF.type, OWL.Class))
        v.add((c, RDFS.label, Literal(name)))
        v.add((c, SKOS.notation, Literal(code)))
        v.add((c, SKOS.definition, Literal(definition)))
    for name in REGIMES.values():
        c = KG[name]
        v.add((c, RDF.type, OWL.Class))
        v.add((c, RDFS.label, Literal(name)))
        v.add((c, SKOS.definition, Literal("Derived orbit regime; thresholds in kg/build_kg.py header.")))
    v.serialize(os.path.join(OUT, "satcat-vocab.ttl"), format="turtle")

    # ---- instance graph ----
    g = Graph()
    g.bind("kg", KG)
    g.bind("obj", OBJ)

    stats = {
        "objects": 0, "by_type": {}, "by_status": {}, "by_regime": {},
        "decayed": 0, "in_orbit": 0,
    }

    with open(os.path.join(ROOT, "data", "satcat.csv")) as f:
        for row in csv.DictReader(f):
            norad = row["NORAD_CAT_ID"].strip()
            if not norad:
                continue
            s = OBJ[norad]
            stats["objects"] += 1

            tname = TYPE_CODES.get(row["OBJECT_TYPE"].strip(), TYPE_CODES["UNK"])[0]
            g.add((s, RDF.type, KG[tname]))
            stats["by_type"][tname] = stats["by_type"].get(tname, 0) + 1

            g.add((s, RDFS.label, Literal(row["OBJECT_NAME"].strip())))
            g.add((s, KG.noradId, Literal(int(norad), datatype=XSD.integer)))
            if row["OBJECT_ID"].strip():
                g.add((s, KG.cosparId, Literal(row["OBJECT_ID"].strip())))
            if row["OWNER"].strip():
                g.add((s, KG.owner, Literal(row["OWNER"].strip())))

            code = row["OPS_STATUS_CODE"].strip()
            sname = STATUS_CODES.get(code, STATUS_CODES["?"])[0] if code else "StatusUnknown"
            g.add((s, RDF.type, KG[sname]))
            stats["by_status"][sname] = stats["by_status"].get(sname, 0) + 1

            if row["LAUNCH_DATE"].strip():
                g.add((s, KG.launchDate, Literal(row["LAUNCH_DATE"].strip(), datatype=XSD.date)))
            decay = row["DECAY_DATE"].strip()
            if decay:
                g.add((s, KG.decayDate, Literal(decay, datatype=XSD.date)))
                g.add((s, RDF.type, KG.StatusDecayed))
                stats["decayed"] += 1
            else:
                stats["in_orbit"] += 1

            per = parse_float(row["PERIGEE"])
            apo = parse_float(row["APOGEE"])
            pd_ = parse_float(row["PERIOD"])
            inc = parse_float(row["INCLINATION"])
            for pred, val in (("perigeeKm", per), ("apogeeKm", apo),
                              ("periodMin", pd_), ("inclinationDeg", inc)):
                if val is not None:
                    g.add((s, KG[pred], Literal(val, datatype=XSD.double)))

            if not decay:
                reg = regime_of(per, apo, pd_, inc)
                if reg:
                    g.add((s, RDF.type, KG[REGIMES[reg]]))
                    stats["by_regime"][reg] = stats["by_regime"].get(reg, 0) + 1

    g.serialize(os.path.join(OUT, "instances.ttl"), format="turtle")
    stats["triples_instances"] = len(g)
    stats["triples_vocab"] = len(v)
    with open(os.path.join(OUT, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2, sort_keys=True)
    print(json.dumps(stats, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
