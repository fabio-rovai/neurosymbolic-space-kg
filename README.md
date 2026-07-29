# Neurosymbolic space knowledge graph

**A knowledge graph of all 70,122 catalogued space objects, aligned to the
Space Situational Awareness Ontology, with the measurement that matters for
AI in orbit: the reasoner can reject almost nothing, and the catalogue can
reject almost everything.**

Maintained by [Tesseract Academy](https://gov.tesseract.academy). Companion
repositories: [industrial-ontology-crosswalks](https://github.com/fabio-rovai/industrial-ontology-crosswalks),
[construction-standards-crosswalks](https://github.com/fabio-rovai/construction-standards-crosswalks),
[space-metrics-crosswalk](https://github.com/fabio-rovai/space-metrics-crosswalk).

## At a glance

- **The graph:** 832,680 triples over 70,122 objects from a pinned CelesTrak
  SATCAT snapshot (2026-07-29): 27,258 payloads, 6,870 rocket bodies, 35,833
  debris objects; 34,711 in orbit, 35,411 decayed; derived orbit regimes
  (28,238 LEO, 1,011 geosynchronous-band, 723 geostationary candidates,
  23 graveyard-region residents).
- **The alignment:** a curated SSSOM crosswalk from the lifted SATCAT
  vocabulary to Rovetto's SSA Ontology (353 classes, the NASA mission-viz
  vendoring): 15 correspondences and 2 asserted non-mappings, every row argued.
- **The headline measurement:** SSAO declares exactly **one** disjointness
  axiom, between two ephemeris *representation formats*. Only 2 of 353 classes
  can ever participate in a provable contradiction. For 99.4 percent of the
  ontology, **no wrong alignment can be rejected by reasoning, ever.**
- **The neurosymbolic answer, quantified:** four deliberately wrong but
  lexically plausible mutant mappings (the kind lexical and embedding matchers
  propose) are all invisible to the reasoner, and all refuted by the instance
  data: payload-equals-operational falls to **9,031** counter-instances,
  geosynchronous-equals-geostationary to **1,007 of 1,011** (99.6 percent),
  rocket-body-equals-payload to **6,870 of 6,870**, decayed-equals-resident to
  **35,411 of 35,411**. Extensional falsification does the work intensional
  semantics cannot.
- **The rules layer:** debris-mitigation signals computed symbolically over
  the graph: a conservative lower bound of **10,016** LEO objects more than
  25 years past launch in a non-mission state (the IADC 25-year rule's
  population), **619** non-operational GEO-band payloads not yet in the
  graveyard region, and **0** decayed-but-operational contradictions inside
  the catalogue itself.

## Reproduce it

```bash
python3 -m venv .venv && .venv/bin/pip install rdflib pyshacl
.venv/bin/python kg/build_kg.py          # SATCAT -> 832k-triple KG + stats
.venv/bin/python gate/mutations.py       # intensional vs extensional falsification
.venv/bin/python rules/compliance.py     # debris-mitigation rule signals
```

## What is here

| Path | What it is |
|---|---|
| [`data/satcat.csv`](data/satcat.csv) | Pinned CelesTrak SATCAT snapshot (2026-07-29). CelesTrak updates daily; the pin makes every number reproducible. |
| [`ontology/SSAO_Rovetto.owl`](ontology/SSAO_Rovetto.owl) | The Space Situational Awareness Ontology (R. Rovetto), Turtle, as vendored by NASA mission-viz. |
| [`kg/build_kg.py`](kg/build_kg.py) | The lift and the graph: SATCAT codes to IRIs, derived orbit regimes with printed thresholds, one node per object. |
| [`crosswalks/satcat-ssao.sssom.tsv`](crosswalks/satcat-ssao.sssom.tsv) | The argued alignment, including the asserted non-mappings (the DEB-to-Fragmentation_Debris trap; decayed objects are not resident). |
| [`gate/mutations.py`](gate/mutations.py) | The falsification harness: disjointness-reachability over SSAO plus instance-level refutation of mutant mappings, with witness counts. |
| [`rules/compliance.py`](rules/compliance.py) | IADC-lineage rule signals with their assumptions stated (launch date as lower bound for mission end). |
| [`SOURCES.lock`](SOURCES.lock) | sha256 pins for the data and ontology snapshots. |

## Why this exists

AI is entering space operations as extractors, matchers and copilots that file
objects, missions and events under ontology terms. This repository measures
what happens when those classifications are wrong: in the domain's best-known
open ontology, the reasoner is silent on 99.4 percent of the vocabulary, so
correctness has to come from somewhere else. The somewhere else is the
catalogue itself: 70,122 instances constitute a refutation machine orders of
magnitude sharper than the schema. Neurosymbolic systems for space should be
built around that asymmetry, neural proposal, symbolic-plus-extensional
disposal, and this repository is a worked, reproducible example.

A detailed study of the method is in preparation; a summary article is on the
[Tesseract Academy research pages](https://gov.tesseract.academy/research).

## License

[CC BY 4.0](LICENSE). SATCAT data courtesy of CelesTrak (T.S. Kelso). The SSA
Ontology is by Robert J. Rovetto. Cite via [`CITATION.cff`](CITATION.cff).
