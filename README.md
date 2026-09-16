# Takeovers Engineering Challenge — Submission Report: Actes Track

**Subject Company:** ARCHEAN TECHNOLOGIES (SIREN `480489707`)  
**Track:** Data / ML Engineer  
**Candidate:** `Tamura-cloud`  
**Detailed Dossier:** See [RELATORIO_TECNICO_PROJETO.md](RELATORIO_TECNICO_PROJETO.md) for the comprehensive 20-year technical breakdown and pedagogical guide.  
**Walkthrough recording (≈3 min):** ⚠️ **_PENDING — paste the Loom link here before opening the PR_**

---

## 1. Executive Summary

This repository contains the complete historical reconstruction of the capital composition of **ARCHEAN TECHNOLOGIES (SIREN 480489707)** across its 20-year operational history (2004–2025), derived from 17 official corporate acts deposited with the French commercial registry (INPI) and 300-DPI OCR layers.

### Key Highlights:
* **`results.json` Deliverable:** Located at repository root, fully compliant and validated against `challenges/actes/schema/results.schema.json`.
* **22 Grounded Events:** Every corporate event carries strict provenance (`inpi_id`, `page`, normalized `bbox [x0, y0, x1, y1]`, and text `snippet`).
* **7 Reconstructed Capital States:** From incorporation at **37.000 €** to the current stable capital of **400.000 €**, closed with 100% share-conservation consistency.
* **62 of 63 invariant checks pass, and the failing one is the point.** `python main.py --audit results.json` reports **REPROVADO** and exits non-zero, on purpose. Invariant #5 (holder continuity) fails between 2006-10-20 and 2008-06-27, which is exactly where four individual shareholders leave the cap table without a naming *cédant* in any Archean act. An audit that returned green here would be the bug, not the feature — the gap is declared rather than smoothed over. See §5.
* **Invariant 7 enforces the brief's own definition.** The brief defines `capital_timeline[]` as *"the state of the cap table after each of those events"*. Invariant #7 checks precisely that: every state's causes must exist and precede it, and every event date must have a state. It is the only check that links the two artefacts — and it is what surfaced a state dated `2005-05-17` whose own cited causes were all from `2005-08-16`.
* **The Group Bonus (`group`):** Reconstructed corporate ownership proving that holding company **HADEAN (SIREN 499979540)** acquired and owns 100% of Archean Technologies.
* **Provenance verified, not asserted:** all **23/23** submitted snippets were re-located inside the shipped OCR, and **19/23** reproduce the declared `bbox` to within 0.002. The remaining 4 are documented ambiguities, not silent guesses. Reproduce with `python main.py --siren 480489707 --benchmark results.json`.
* **Contradictions found and declared:** three material discrepancies inside the acts themselves (Acts 3, 4 and 15), six OCR transcription errors on pages we actually cite — including a **factor-1000 misread** (`200.0euros` where the document reads `200.000 euros`) — and one share-allocation error *we made ourselves* and corrected against the scanned image. All are listed in `results.json.notes`.
* **Zero External API Cost:** `results.json` is assembled by local Python and needs no paid endpoint — no network access is required to reproduce or verify the submitted artefact.
* **How the timeline was built, stated plainly:** the seven Archean states were **typed by hand** in `reconcile_timeline.py::build_timeline()` after reading the acts, then machine-checked. They are **not** derived from the `events` array. That distinction matters and §3 spells out what it costs. The derivation engine (`src/ledger.py`) is real and is used — but on the other companies, not on the submitted file.

---

## 2. How to Run

### Requirements
```bash
pip install -r requirements.txt
```

### Reproduce the submitted artefact
```bash
python reconcile_timeline.py
```
Rebuilds `results.json` from the hand-assembled states in `reconcile_timeline.py`, re-checks the algebraic invariants across all seven epochs, and validates the output against `challenges/actes/schema/results.schema.json`. Deterministic, offline, and requiring no credentials.

### Verify what is claimed (no API key needed)
```bash
# Seven invariants + schema, against the submitted file
# Expected: 62/63 and exit code 1. The single failure is invariant #5, the
# declared 2008 gap — see §5. A green run here would mean the check is broken.
python main.py --audit results.json

# Re-locate every snippet in the shipped OCR and diff the bbox against the claim
python main.py --siren 480489707 --benchmark results.json

# Point out OCR transcription errors (optionally restricted to cited pages)
python main.py --siren 480489707 --ocr-errors --benchmark results.json

# Where does a phrase sit, in submittable coordinates?
python main.py --siren 480489707 --ground "Le capital social est fixé à la somme de trente sept mille"

# See the capital evolve: composition bar per state, and — beside each citation —
# the crop of the actual page it was read from, so the claim shows its own proof.
# Add --sem-imagens for the text-only version (29 KB instead of 2 MB).
python main.py --timeline-html results.json
```
`--benchmark` is the check that matters: it answers *"do the boxes point where you say they do?"* without trusting either the OCR or our own claims.

### Any company in the corpus — and the optional LLM reader

Nothing in `src/` is Archean-specific. Given a SIREN, the same code triages the corpus, grounds the citations and derives the ledger:

```bash
# Read a company's OCR with DeepSeek, propose events, then ground + verify them
python main.py --siren 820561470 --extract --output results_pautet_llm.json

# Same destination, but from events a human already wrote
python main.py --events events/events_820561470.json --output results_820561470.json
```

**SARL PAUTET (SIREN 820561470)** is carried in this repository as a control case, because its cap table was read by hand first, boxes included. The timeline derived from the model's reading is **identical field by field to the hand-derived one** — 1 000 shares in 2016 and 15 000 in 2022, same holders, same dates — and both pass every invariant. The model emitted 2 events where the human emitted 5; both routes land on the same cap table. The raw model proposal is frozen to `events/events_820561470_candidate.json` so that the *unverified* reading can still be audited after the fact.

### Inspect Visual Grounding (Bounding Boxes)
To verify any event's red bounding box drawn directly over the original scanned document:
```bash
# Example: Incorporation capital (Act 1, Page 3)
python quick_check.py --doc 1 --page 3 --bbox [0.1201, 0.3994, 0.6591, 0.4146]

# Example: 50.000 € Capital Increase (Act 4, Page 3)
python quick_check.py --doc 4 --page 3 --bbox [0.0499, 0.1685, 0.9479, 0.2007]
```

---

## 3. Trade-offs Made

1. **Hand-assembled timeline, machine-checked arithmetic.**
   The seven Archean states were **assembled by hand** in `reconcile_timeline.py::build_timeline()`: each holder, share count and percentage was read from the acts and typed in as a literal. They are **not** derived from the `events` array — the two are parallel hand-authored artifacts.

   That trade-off has a cost, and it should be named rather than hidden: **two hand-authored artifacts can drift apart, and nothing in the build catches it.** The invariants check the timeline's internal arithmetic, not that it follows from the events. What they *do* catch is real — share closure, capital identity, percentage closure, flow conservation, date consistency — and they are what surfaced the 803/637 transposition in §4.

   `src/ledger.py` is a genuine derivation engine, and the PAUTET control case in §2 is produced by it end to end, events to states, with no typed balances. It does **not** produce the Archean timeline. Run it on the submitted events and you get **370 shares at 2005-05-17 instead of 1 500**, because the events do not carry the share allocation of each intermediate capital movement, and the 2005-08-16 transfer names sources (GUELLATI, LEROUX, ROUJEAN) who never enter the cap table in the event list at all. Closing that gap means sourcing an allocation event for every intermediate increase — an honest next step, not a claim we can make today.
2. **Normalized Bounding Boxes (0.0 to 1.0) vs. Raw OCR Pixels:**  
   While raw OCR polygons are provided in 300-DPI pixels, our pipeline dynamically translates them using the PDF point geometry (measured dynamically per page via PyMuPDF `page.rect`, typically $\sim 1654 \times 2353$ pt for these scanned dossiers $\times \frac{300}{72}$) into normalized coordinates `[x0, y0, x1, y1]`, ensuring exact resolution-independent rendering matching `tools/bbox_viewer.py`.
3. **Ergonomic CLI Tooling:**  
   `tools/bbox_viewer.py` was wrapped by `quick_check.py` to eliminate repetitive manual path typing, and enhanced to accept flexible BBox inputs (with/without brackets, spaces, or commas).

---

<a id="ai-tools"></a>
## 4. How I used AI

The brief asks for this section by name and asks that the tools be named. What was actually used: **GitHub Copilot** (DeepSeek V4.1 Flash) in VS Code agent mode, as an interactive senior engineering mentor and pair programmer. **DeepSeek** (`deepseek-chat`, temperature 0) is additionally wired into the optional extractor described in §2. Earlier scoping drafts also leaned on Claude and Gemini.

* **What was delegated to AI:**
  * Drafting high-efficiency extraction boilerplate and PyMuPDF coordinate geometry math;
  * Automated JSON schema validation using `jsonschema`;
  * Scanning and cataloging the 17 legal acts to index filing decisions and dates.
* **What was checked and verified by the candidate:**
  * The algebraic reconciliation of share counts across all seven epochs, re-run end to end after every edit;
  * The three material discrepancies in Acts 3, 4 and 15, each confirmed against the **rendered page image**, not against the OCR text — the OCR is the input under suspicion, not the source of truth;
  * The 2005 share allocation, where our own ledger read `803/637` while the document says `823/617`. The OCR was right and we were wrong: a digit transposition that only surfaced when the snippet↔bbox cross-check was pointed at the cap table;
  * Folder organisation, and confirming that no secret, token or `.env` file is committed.
* **Where AI required critical steering — and where it led us wrong:**
  * AI initially explored building an abstract graph engine (`networkx`); this was steered back to a deterministic state-transition ledger to avoid premature abstraction and respect the time budget.
  * AI scripts initially outputted BBox CLI inputs requiring strict comma formatting without spaces; this was caught during visual testing and refactored into a resilient parser.
  * **The pipeline silently dropped every event it could not ground.** The brief says the opposite — *"an event you cannot ground is still worth reporting, with a note saying so"*. The behaviour was inverted once the brief was re-read against the code.
  * **An early audit treated the OCR text as ground truth.** It graded the JSON against the OCR, so any snippet disagreeing with a corrupt OCR line looked fabricated. Rendering the page proved the reverse in at least one case: the image reads `(37.000)` while the OCR says `(37.0o0)`. The verification order had to be inverted — image first, OCR only as a locator.
  * **A confidence-based error filter was tried and rejected.** Filtering OCR lines by their `score` finds nothing useful: the provably wrong line `(37.0o0)` scores **0.988**, against a corpus median of 0.991. Detection had to move to numeric-token patterns, which is what `src/ocr_audit.py` now does.
  * **The `allocation` semantics were wrong in my code, not in the model's reading.** On the PAUTET control case the model reported 7 140 and 6 860 *new* shares for the 2022 reserves incorporation. My ledger **assigned** them instead of **adding** them, producing 14 000 shares against a capital of 150 000 € at a 10 € nominal — a 15× error in the denominator of the cap table. The act's own share numbering ("de 1 à 510 et de 1001 à 8140") proves the model right and the ledger wrong. The model also flagged an internal contradiction in the document itself (the text says 6 850 new shares, the articles say 7 350 total) and resolved it correctly from the updated articles. Fixed by making `allocation` additive; the same lesson as the 803/637 transposition, from the other direction: the arithmetic is ground truth and does not care who wrote the claim.

---

## 5. What Was Left Undone & Next Steps

**Unresolved, and declared as such in `results.json.notes`:**

* **The 2008 exits are reconstructed, not documented.** Between 2006-10-20 and 2008-06-27 the four individual shareholders (Blanco, Aumont, Gicquel, Capgras) leave the cap table, yet the 2008 act never names a *cédant*: HADEAN simply appears as *Associée Unique*. Inferring the exits from that wording is legitimate under `event_codes.json`, which states that `SHAREHOLDER_END` is *"most often reconstructed by diffing the pre- and post-act capital-allocation article"* — but the transfer date is not something we can point at, so no `SHAREHOLDER_END` events were emitted. Our own invariant #5 flags this gap instead of hiding it.
* **Two bounding boxes are ambiguous by construction.** `evt_2005-08-16_exit_leroux` and `evt_2005-08-16_exit_roujean` quote phrases that occur **twice on the same page**; the matcher grounds the first occurrence, which is not provably the intended one.
* **Six OCR errors sit on pages we actually cite**, all with high confidence scores (0.956–0.988). Every submitted snippet uses the correct value, but the OCR corpus itself was not rewritten.

**Explicitly out of scope:**

* **Multi-hop Group Traversal:** we proved the parent link to **HADEAN (SIREN 499979540)** and the contractual counterparty **ARCHEAN INTERNATIONAL**, but did not expand into Hadean's own upstream shareholders. The brief warns the chain does not stop at one hop, and some of those links live only in the *bilans*, which belong to the other challenge.
* **Scaling:** across 10,000+ companies, a deterministic ledger plus a lexical pre-filter should be complemented by a vision-language model reading the **rendered page**, not the OCR text, to propose candidate events. The *bilan* brief explicitly sanctions this approach.

---

## 6. Environment & Credentials Disclosure

* As required by the briefing, this submission includes a **`.env.example`** naming every variable the code reads, with no values in it.
* **The submitted `results.json` requires no keys at all.** It is produced locally by `reconcile_timeline.py`, and every verification command below runs offline. The brief explicitly notes this is *"a legitimate and interesting answer"*.
* The repository also contains an **optional** semantic extractor (`src/extractor_llm.py`) that calls a DeepSeek endpoint through the OpenAI-compatible SDK. It is **not** on the path that produced the submitted artefact, its output is gated behind the same grounding and invariant checks as everything else, and it stays disabled unless `DEEPSEEK_API_KEY` is set — `python main.py --offline` exercises the full pipeline without it.

---

## 7. Document Triage Matrix (Summary of the 17 Acts)

| Act | Filing Date | Document Subject | Decision | Legal / Scope Rationale |
| :---: | :---: | :--- | :---: | :--- |
| **1** | 2005-01-25 | Constitution | **INCLUDED** | Baseline state: 37.000 € initial capital, 3 founding shareholders. |
| **2** | 2006-01-03 | Constatation d'augmentation | **INCLUDED** | 1st Capital Increase (+113.000 € $\to$ 150.000 €). |
| **3** | 2006-01-04 | Cession d'actions / Sortie | **INCLUDED** | Exit of 3 temporary investors; rectification of protocol error. |
| **4** | 2007-02-20 | Augmentation du capital social | **INCLUDED** | 2nd Capital Increase (+50.000 € $\to$ 200.000 €) and entry of Michel Capgras. |
| **5** | 2008-06-23 | Rapport avantages particuliers | **INCLUDED** | CAA report on creation of Class A & B preference shares (`CAPITAL_DUAL_CLASS`). |
| **6** | 2008-07-15 | Augmentation du capital social | **INCLUDED** | Split 100:1, acquisition by HADEAN, issuance of A & B shares (368.102 €). |
| **7** | 2008-09-08 | Rapport complémentaire | *Annex* | Technical complement to Act 6 preference share valuation. |
| **8** | 2010-12-08 | Changement d'objet social | **EXCLUDED** | Out of scope: Corporate object change; capital remained unchanged at 368k €. |
| **9** | 2010-12-08 | Changement d'objet social | **EXCLUDED** | Duplicate/extract of Act 8. |
| **10** | 2011-07-11 | Date de clôture | **EXCLUDED** | Out of scope: Fiscal year closing date change. |
| **11** | 2011-07-11 | Date de clôture | **EXCLUDED** | Duplicate/extract of Act 10. |
| **12** | 2013-02-12 | Transfert de siège social | **EXCLUDED** | Out of scope: Address transfer to Avenue d'Italie; capital unchanged at 368k €. |
| **13** | 2017-01-20 | Réduction du capital social | **INCLUDED** | EGM authorization to reduce capital by buying back and cancelling 150.861 B shares. |
| **14** | 2017-03-28 | Réduction du capital social | **INCLUDED** | Realization of capital reduction to 217.241 €; exit of the 4 VC funds. |
| **15** | 2018-05-30 | Augmentation du capital social | **INCLUDED** | Capital increase to 400.000 € via reserves incorporation for HADEAN. |
| **16** | 2018-11-02 | Démission de commissaire | **EXCLUDED** | Out of scope: Statutory auditor resignation. |
| **17** | 2025-12-02 | Approbation des comptes | **EXCLUDED** | Out of scope: Ordinary annual approval of 2023 accounts; capital stable at 400k €. |

---

<a id="submitting"></a>
## Submitting

`challenges/actes/BRIEF.md` links to `../../README.md#ai-tools` and `../../README.md#submitting`.
Those two anchors are defined in this file, so the brief's own links resolve inside this repository.

**What is submitted:** `results.json` at the repository root (the Actes deliverable), plus the code
that produced it and the code that audits it. The submitted artefact needs no API key and no network.

**Layout:** `src/` is the reusable pipeline (loader, pre-filter, grounding, ledger, validator,
reports); `main.py` is the CLI; `reconcile_timeline.py` is the Archean-specific assembler behind the
submitted file. `events/` holds the events as data — the *reading* — deliberately separated from the
code that checks it. `data/` is the third-party corpus: untracked, both for size and because the
corpus `NOTICE.md` asks that it not be redistributed.

---
*Takeovers SAS Engineering Challenge Submission — September 2026*
