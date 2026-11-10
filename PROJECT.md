# Project: Remediate Marche-Public-Skill Audit Findings

## Architecture
- Modules:
  - `scripts/analyse_marche.py`: DCE document analysis, buyer extraction, criteria, traps, non_extrait fields.
  - `scripts/go_nogo.py`: Multi-criteria Go/No-Go evaluation engine, scoring table exploitation, red flags.
  - `scripts/checklist_pieces.py`: Physical disk file existence verification, 4D document status model.
  - `scripts/matrice_conformite.py`: Compliance matrix generation (JSON, MD, XLSX) with distinct NON_VERIFIE tracking and confidence metrics.
  - `scripts/controle_prix.py`: DPGF arithmetic verification, line items extraction requirement, decoupled OAB detection.
  - `scripts/controle_final.py`: Pre-submission readiness gate, incomplete status blocking, [À FOURNIR] blocking, page limits.
  - `evals/score_eval.py`: End-to-end evaluation benchmark executing genuine pipeline against fixtures with CI non-zero exit code.
  - `assets/seuils.yaml` & `references/02-procedures-et-seuils.md`: Public procurement thresholds (Décret n° 2025-1440, 100 k€ effective 01/04/2026).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Profile Schema Alignment | Support effectifs.total_salaries, identite.siege_social.code_postal, and cost structure variations | M1 | Survey O1-O3 |
| 2 | Site Visit Requirement Parsing | Correct pieces_exigees dict parsing and visite_effectuee flag | M1 | Survey O4 |
| 3 | Blocking Contradiction Red Flag | Red flag / NO-GO verdict strictly triggered when blocking contradictions exist | M1 | Survey O5 |
| 4 | Config Exploitation in Go/No-Go | Fully exploit weights, thresholds, scoring tables from go_nogo_config.yaml | M1 | Survey O6 |
| 5 | Remove Fallback 'or True' | Eliminate artificial 'or True' bypasses in checklist checks | M2 | Survey O7 |
| 6 | Physical File Presence Check | Verify actual disk presence instead of inferring from YAML metadata (police numbers) | M2 | Survey O8 |
| 7 | 4D Document Status Model | Strictly separate required by contract, physically present, legally valid, content-verified | M2 | Survey O9 |
| 8 | Incomplete Status Ineligibility | Treat A_COMPLETER, A_METTRE_A_JOUR, NON_VERIFIE, A_CHIFFRER, A_REDIGER, A_FINALISER, A_OBTENIR as ineligible | M3 | Survey O10 |
| 9 | Residual Placeholder Rejection | Residual [À FOURNIR] tags must set final verdict to PAS_PRET | M3 | Survey O11 |
| 10 | RC Page Limit Enforcement | Enforce technical proposal page limit if specified in RC | M3 | Survey O12 |
| 11 | Compliance Matrix NON_VERIFIE Tracking | nb_non_verifie counter in JSON, distinct display without non-compliant conversion, confidence metric | M4 | Survey Obs 2 |
| 12 | Market Analysis non_extrait Preservation | Prevent non_extrait list overwrite in analyser_marche | M4 | Survey Obs 3 |
| 13 | Buyer Extraction Cleanup | Extract buyer without capturing newline or trailing lines, handle casing | M4 | Survey Obs 3 |
| 14 | Criteria Weight Sum to 100% | Validate selection criteria weights sum to exactly 100% | M4 | Survey Obs 3 |
| 15 | Decouple DPGF Arithmetic and OAB | Separate arithmetic verification errors from statistical OAB suspicion | M5 | Survey Obs 4 |
| 16 | Reject Empty DPGF Compliance | Fail compliance if zero exploitable line items extracted from DPGF | M5 | Survey Obs 4 |
| 17 | Regulatory Reference 100k€ Update | Set effective date 01/04/2026 per Décret n° 2025-1440 across yaml and markdown docs | M5 | Survey Obs 4 |
| 18 | E2E Evaluation Benchmark Pipeline | Refactor evals/score_eval.py to run genuine extraction against fixtures | M6 | Survey Obs 5 |
| 19 | Benchmark CI Non-Zero Exit Code | Exit with code 1 upon benchmark failure or regression | M6 | Survey Obs 5 |
| 20 | E2E Test Suite (Tiers 1-4) | Comprehensive test coverage across all features | E2E | Dual Track |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Go/No-Go Engine & Profile Alignment | R1 (Features 1, 2, 3, 4) | none | DONE (108 tests passing, Gate PASS) |
| M2 | Administrative Checklist & Physical Verification | R2 (Features 5, 6, 7) | none | PLANNED |
| M4 | Compliance Matrix & Market Analysis | R4 (Features 11, 12, 13, 14) | none | PLANNED |
| M5 | Pricing, OAB & Regulatory Thresholds | R5 (Features 15, 16, 17) | none | PLANNED |
| M3 | Final Control & Incomplete Status Handling | R3 (Features 8, 9, 10) | M2, M5 | PLANNED |
| E2E | E2E Testing Suite Track | Feature 20 (Tiers 1-4) | none | PLANNED |
| M6 | Final Milestone: E2E Benchmark Pass & Hardening | R6 (Features 18, 19, pass E2E tests, Tier 5 hardening) | M1, M2, M3, M4, M5, E2E | PLANNED |

## Code Layout
- `scripts/go_nogo.py`: Owned exclusively by M1
- `scripts/checklist_pieces.py`: Owned exclusively by M2
- `scripts/matrice_conformite.py`: Owned exclusively by M4
- `scripts/analyse_marche.py`: Owned exclusively by M4
- `scripts/controle_prix.py`: Owned exclusively by M5
- `assets/seuils.yaml`: Owned exclusively by M5
- `references/02-procedures-et-seuils.md`: Owned exclusively by M5
- `scripts/controle_final.py`: Owned exclusively by M3
- `evals/score_eval.py`: Owned exclusively by M6
- `tests/test_remediation_e2e.py`: Owned by E2E Testing Track

## Interface Contracts
### `scripts/go_nogo.py`
- `evaluer_go_nogo(analyse: dict, profil: dict, config: dict = None) -> dict`:
  - `verdict`: `"GO"` | `"NO-GO"` | `"A_DISCUTER"`
  - `drapeaux_rouges`: list of red flag objects `[{"code": str, "description": str, "bloquant": bool}]`
  - Invariance: If any `c in analyse.get("contradictions_detectees", [])` has `c.get("gravite") == "BLOQUANT"`, `verdict` MUST be `"NO-GO"` and a red flag `"CONTRADICTION_CONTRACTUELLE_BLOQUANTE"` must be raised.

### `scripts/checklist_pieces.py`
- `generer_checklist(dce_analyse: dict, profil: dict, dossiers_docs: list = None) -> dict`:
  - Document status 4D model: `exige_par_marche: bool`, `present_disque: bool`, `valide_juridiquement: bool`, `verifie_contenu: bool`, `statut: str`.
  - No `or True` fallbacks.
  - Physical disk check calls `verifier_presence_fichier` against actual paths in `dossiers_docs`, no fallback on `numero_police` or profile metadata.

### `scripts/controle_prix.py`
- `verifier_arithmetique(lignes: list, total_excel: Decimal, tva: Decimal) -> dict`:
  - `statut_global`: `"CONFORME"` | `"NON_CONFORME"`
  - If `len(lignes) == 0`: `statut_global = "NON_CONFORME"`, anomaly `"DPGF_VIDE_OU_NON_EXPLOITABLE"`.
  - `anomalies`: contains ONLY arithmetic errors (multiplication, addition, discrepancies).
  - `alerte_oab`: separate boolean flag / dictionary, NOT merged into arithmetic `anomalies`.

### `scripts/controle_final.py`
- `controler_dossier_final(analyse: dict, go_nogo: dict, checklist: dict, matrice: dict, prix: dict, memoire_texte: str = "", config: dict = None) -> dict`:
  - Incomplete statuses: any piece in checklist with status in `["A_COMPLETER", "A_METTRE_A_JOUR", "NON_VERIFIE", "A_CHIFFRER", "A_REDIGER", "A_FINALISER", "A_OBTENIR", "MANQUANT", "A_FOURNIR", "EXPIREE"]` produces a blocking item (`blocages`).
  - Residual placeholders: `re.search(r"\[(?:À|A)\s*FOURNIR\]", memoire_texte, re.I)` produces a blocking item (`blocages`), forcing `statut_code: "PAS_PRET"`.
  - RC page limit: if `analyse.get("rc_limite_pages")` is set and page count exceeds limit, produces a blocking item.
