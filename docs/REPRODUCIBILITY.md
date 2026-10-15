# Reproducibility: verification is not a new vintage

## Recorded environment and scope

The completed locked forecast evaluation uses Python 3.12 in the project-local `.venv`, with exact resolved versions in `requirements.lock`. `scripts/bootstrap.ps1` creates that environment with `py -3.12`, installs the lock using binary wheels and installs the local package without dependency resolution. When the machine-local `configs/project.yaml` exists it then runs `scsi preflight`. Otherwise installation succeeds in portable-replay mode, without creating a configuration or acquiring data. No global kernel, shell configuration, account or cloud changes are required.

The final lock is `artifacts/protocol_lock.json`, SHA-256 `1d853f3d8a9e9185cbaad64b44d20d7630a239c2bf45ac405fd8e90e9400fda0`. It hashes the critical code, configuration, canonical targets and flow, source manifests, crosswalk, 2023 selection and measurement-pilot freeze. Its 2024–2025 evaluation contains nine prespecified experiments, 1,080 saved forecasts and **24 distinct forecast months**.

These are current-vintage observations retrieved in October 2026, not historical first-release archives. Reproducing the arithmetic with the same bytes is different from reconstructing a historical information set. A new provider retrieval can revise history, and must not overwrite the original snapshot or reuse its lock identity.

The separate NOAA measurement is accepted for all **366 days of 2024**: **12,408,103 cleaned cargo-proxy points**, **23,986 candidate episodes**, **1,098 gateway-day summaries** and **21 gateway/scenario sensitivity rows**. Its 60 reviewed trajectory examples remain the original 14-day pilot sample. `geo_finalization_state.json` and `geo_measurement_receipt.json` link the accepted artifacts; `geo_independent_acceptance_verification.json`, retained in the original local workspace rather than distributed here, records the subsequent all-crop hash verification. Measurement acceptance does not establish vessel-detection completeness, operational agreement or a forecasting edge.

## Portable public-aggregate reproduction

This public repository, derived from the reviewed source bundle, omits the machine-specific original configuration and raw vendor/NOAA panels. It includes `configs/project.template.yaml` with null workspace/website paths, package code, the dependency lock and the transformed public results. For a fresh clone on Windows:

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install --only-binary=:all: -r requirements.lock
.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .
.venv/Scripts/python.exe scripts/reproduce_public.py
```

This root-relative script needs no original absolute configuration and no account. It recomputes 30 displayed metric rows from 720 public forecast records, plus both primary paired comparisons and their three-/six-month bootstrap intervals. It writes `artifacts/audit/public_reproduction_receipt.json`. These six availability specifications are the public display scope; the full local study additionally retains three changed-target exclusion experiments. Public reproduction is arithmetic replay, not acquisition or model re-fitting. The executed notebooks can be inspected in the bundle, but reexecuting their source/measurement checks needs the retained local inputs described below.

## Original local workflow (not runnable from this public checkout)

The commands below document the original full-evidence workspace. They require retained source panels and the frozen machine configuration, neither of which is distributed here. Use the public replay above for this repository:

```powershell
.venv/Scripts/python.exe -m pytest tests -q
.venv/Scripts/python.exe notebooks/verify_locked_predictions.py
.venv/Scripts/python.exe notebooks/execute.py
.venv/Scripts/python.exe -m scsi.cli evaluate-locked --config configs/project.yaml
```

The independent audit recalculates all 45 model/experiment metric rows using scalar arithmetic, checks all 1,080 forecasts against target aggregation and declared information clocks, reconstructs fitted ridge outputs from their stored coefficients/scalers, and independently draws the four primary paired bootstrap intervals. It does **not** select models, refit the study or independently validate source observations. The saved receipt is `artifacts/audit/independent_research_audit.json`; it identifies its own script and input hashes.

`evaluate-locked` verifies the frozen critical inputs, selection and prediction hashes. If `locked_results.json` already exists, it verifies and returns that result. It does not claim to refit predictions on that path. A scratch replication requires preserving the original artifacts and independently executing the specified package functions in a separate output directory under a new run receipt—not deleting the original result to make it run again.

## Notebooks and their execution boundary

`notebooks/execute.py` executes both notebooks sequentially with the current project Python interpreter. A temporary kernel specification, connection files, IPython cache and Matplotlib cache live only under `artifacts/notebook_runtime`. The kernel specification contains a machine-local interpreter path and is excluded from public evidence. The runner shuts down kernels, removes its temporary specification directory and records input/output hashes, code-cell counts, displayed output types, elapsed time and failures in `artifacts/audit/notebook_execution.json`.

- `01_measurement_audit.ipynb` imports the package cleaning, geofence, reconstruction and daily-summary functions. It reads only one already-acquired source day for a bounded worked example, and displays the existing measurement coverage and attributed geometry/audit image. The one-day example is left/right censored and is not a fresh full-year reconstruction.
- `02_locked_research.ipynb` imports `verify_lock`, `metrics` and `paired_bootstrap`, reads immutable predictions and reproduces actual comparison tables and figure displays. It performs no training or data acquisition.

Executed notebook outputs are saved with the notebooks. After accepted final geospatial outputs **and** regenerated report figures are ready, run `.venv/Scripts/python.exe notebooks/execute.py` to execute **both** notebooks. Refreshing only the measurement notebook would leave stale figure captions or hashes in the research notebook. The runner's `--only` option is useful during development, not the final release procedure. No pilot output is silently relabeled full year.

At this accepted full-year checkpoint, both notebooks were executed together after report regeneration: **5/5 measurement code cells** and **6/6 research code cells**, with one and three embedded PNG outputs respectively and no error outputs. A separate receipt check verified all **24 recorded input hashes**, both executed-notebook hashes and both source-cell hashes against the current files; `artifacts/audit/notebook_full_year_verification.json`, retained in the original local workspace rather than distributed here, records that check. The temporary kernel-specification directories were removed. This execution is a bounded evidence replay, not a second full-year measurement or external human review.

## Acquisition and stage commands (original full-evidence workspace)

The existing CLI is `python -m scsi.cli COMMAND --config configs/project.yaml`. The inspected commands are:

1. `preflight`, `audit-sources`.
2. `acquire-targets`, `acquire-flow`, `build-crosswalk`.
3. `acquire-ais --pilot`, then `audit-ais` to measure and freeze exactly 14 verified days.
4. `acquire-ais --resume`, then `build-geospatial` for the acquired 2024 scope.
5. `build-features`, `validate-models`, `lock-protocol`.
6. `evaluate-locked`, `run-robustness`, `build-report`, `build-site-data`, `verify-release`.

`scripts/run_core.ps1` wraps that sequence with an exclusive local execution lock. In a locked workspace, `audit-sources`, target/flow acquisition and crosswalk commands verify frozen inputs with zero network requests. An existing `audit-ais` freeze is checked against the geometry hash and geospatial settings, then returned without rerunning the pilot. A new pilot reads exactly the first 14 days, while later full measurement preserves the reviewed trajectory audit. These explicit branches make completed-stage replay possible without treating a full-year manifest as a new pilot. Actual downloads remain bounded and checksum-verified; the generic CLI `--resume` flag alone is not proof that every arbitrary partial state is recoverable.

In a clean unlocked run, `audit-sources` performs the bounded discovery in `scsi.sources.discovery`: nine metadata/sample responses establish the BTS target schema/license and four-port sample, official PortWatch catalog ownership/services, explicit FAQ API access, methodology and selected gateway identities. This creates the exact metadata files required by the target, flow and crosswalk adapters before panel extraction. Schema, license, permission or identity changes stop the stage for source review; a new download is never inserted into the frozen original run. A separate real-response smoke verified this path without acquiring new bulk panels.

After accepted finalization, `build-geospatial` verifies the linked measurement, code, geometry, freeze, audit, source manifest and all 366 crop hashes, then returns the existing receipt unchanged. It does not overwrite the accepted measurement. Fresh current-code builds receive `acceptance_mode: current_implementation_no_legacy_rebuild` and a linked `geo_build_acceptance_receipt.json`. This study's original worker exited at 265 acquired partitions, before full-year measurement; its helper rejected acceptance. The one-shot recovery resumed verified crops with current code and used the canonical `build-geospatial` stage for the first full-year measurement. All 366 days were acquired, and acceptance completed on October 15, 2026 at 21:43:52 UTC, followed by an independent all-crop/artifact verification. The 14-day pilot remains separately preserved and is not relabeled as full year.

The separate `.venv/Scripts/python.exe -m scsi.geo.finalize` entry point is only for a run with genuine completed legacy full-year outputs. It preserves those outputs and compares correction effects, **after** the acquisition/initial measurement process has exited and before acceptance. It is not this study's recovery route, not the routine replay command, and must not run concurrently with an acquisition worker. A fresh build does not invent legacy outputs, a before/after correction comparison, or a `geo_postfreeze_correction_receipt.json`.

The archive checker (`scripts/check_public_bundle.py`), wheel checker, release CLI and orchestration wrapper require the original local release/configuration inputs; they are not public-checkout quickstart commands. After report/site-data generation the wrapper runs the independent arithmetic audit, both notebooks, `pytest` with `artifacts/test-results/pytest.xml`, research release verification and the extracted public-bundle replay, checking every exit code. It limits native numerical pools to one thread in its own process environment and restores prior values on exit. Portfolio build/browser checks, final Git/file manifests and `HANDOFF.md` remain separate completion gates; the research evidence receipt alone does not certify the website or publish anything.

The configuration records the original absolute workspace and website paths. On another machine, the root-relative offline audit/notebook scripts can inspect a copied evidence workspace while leaving frozen configuration bytes unchanged. Full orchestration on different paths requires a **new-run configuration and lock**, not editing the historical configuration and pretending the old hash still applies.

### New source runs are outside this public replay

The source-acquisition and initialization scripts are retained for inspection, not offered as a turnkey end-to-end reproduction from this checkout. In particular, the original project brief, private source snapshots and frozen machine configuration are not distributed. `scripts/initialize_config.py` requires a separately supplied project brief and refuses initialization over historical evidence. Do not run `bootstrap.ps1 -InitializeNewRun` or `run_core.ps1` in this repository.

A new source study needs a separate clean workspace, a reviewed study brief and configuration, current source/geometry review, permitted acquisitions, and genuine pilot trajectory review. Its new vintage and lock must remain distinct from this historical study. A clean current-vintage run was not executed end to end for this publication. Source discovery and initialization were separately tested; that does not make the public checkout a full-source replication package.

Raw NOAA partition/crop caches and canonical vendor panels are not public redistribution bundles. Do not replace frozen observations with newer downloads or bypass provider access restrictions. See `docs/DATA_ACCESS_AUDIT.md`, `data/source_registry.yaml` and `DATA_LICENSES.md`.

## Resource controls and timing

The declared limits are 8 threads, 48 GiB RAM, 80 GiB project storage, 16 GiB raw cache, 20 GiB free-disk reserve, 200 GiB total network transfer, at most two requests in flight per provider, one request/second initially and five attempts. The source downloader honors Retry-After delay-seconds and HTTP dates, with jittered fallback. No notebook performs network I/O. The independent numerical audit runs with one BLAS thread and streams its scalar bootstrap rather than materializing a large resample cube.

Full-year AIS acquisition/measurement is the resource-heavy stage; use the actual acquisition and measurement receipts, not an inferred completion percentage. The completed fresh measurement reports 999.64 seconds. Minute-spaced recovery-controller samples observed at most 8.71 GiB worker-tree RSS and at least 63.70 GiB free disk; these sampled observations are not continuous lifetime peaks. The independent audit's RSS/free-space observation is **not** a peak-resource certificate for the whole project.

## What can and cannot be reproduced from published aggregates

The public transformed forecast export and result tables permit inspection of the stated comparison. Exact raw-source acquisition and re-fitting require the retained permitted snapshots, the frozen environment, and original schema/version checks. Original provider bytes, vessel identifiers, licensed financial inputs from unrelated portfolio studies and private local paths are not included in the public site.

The evidence supports a bounded historical finding: geography WAPE 11.21%, aggregate 11.89%, selected calls-to-TEU benchmark 7.34%. It does not support verified days-before-release, live operational forecasting, independently validated maritime delay, or prospective investment performance. Local tests and agent-assisted arithmetic reconciliation are not external human certification.
