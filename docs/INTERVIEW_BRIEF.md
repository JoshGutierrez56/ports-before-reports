# Ports Before Reports: interview brief

## 60-second explanation

I asked whether keeping the geography of shipping activity helps forecast monthly loaded imports before the full month is reported. I used three gateways—San Pedro Bay, New York/New Jersey and Savannah—with official loaded-import TEUs and container-specific PortWatch calls. I froze the comparison before inspecting 2024–2025 forecast performance.

The answer is qualified, not a model win. Geographic shipping had 11.21% weighted absolute error versus 11.89% for aggregate shipping, but its uncertainty interval included no improvement. A simple calls-to-TEU benchmark selected on 2023 validation did substantially better at 7.34%.

The main contribution is making that comparison auditable: exact source definitions, a nonduplicating gateway crosswalk, release-aware fitting, a common missing-data fallback and paired calendar-block uncertainty. A separate NOAA AIS layer distinguishes activity from possible friction, but cargo codes and reception gaps prevent calling it verified container congestion. This is current-vintage historical research, not a point-in-time or live forecasting claim.

## Three-minute technical walkthrough

**Question and measurement.** The target is the sum of monthly loaded-import TEUs at four reporting ports mapped into three gateways. Los Angeles and Long Beach have separate official target records but a combined PortWatch activity identifier. I checked the exact loaded-import category rather than substituting total TEUs, estimated tons or all-vessel counts. The source panels contain 336 port-month targets and 7,671 gateway-days. Documented PortWatch blackout days become missing, not zero traffic.

**Information set.** Each forecast is as of the end of day 21 UTC, represented by midnight starting day 22. The primary assumed shipping lag is seven days, so the latest usable full daily observation is day 14. Target first-release timestamps are unknown, so 60- and 90-day label-release rules are explicit assumptions. The historical series has current revisions, including a July 2026 PortWatch update; chronological splitting alone cannot make it point-in-time.

**Comparison.** I compare prior-year seasonality, released-target history, aggregate activity ridge, geographic activity ridge, and a training-only median TEU-per-call conversion. Geographic ridge has eight inputs: two released-target history features and two trailing activity windows for each of three gateways. The aggregate ridge has the same history plus two aggregate windows. Scaling is fitted on each training set. Penalties come only from 1, 10 and 100 using 2023 validation. Coefficients can expand as earlier test-period labels become available, but model choices stay frozen.

**Result and uncertainty.** The candidate's 11.21% WAPE is modestly below aggregate shipping's 11.89%. The 5.69% relative improvement has three-month-block interval −23.28% to +30.93% and six-month interval −28.18% to +25.22%. Both include zero. The preselected calls-to-TEU benchmark has 7.34% WAPE; the geographic model's error is 52.71% higher. There are 24 test months, not 1,080 independent tests. Three origins use the same seasonal fallback for every model. Longer availability lags weaken the geographic comparison, so I would not promote it as the preferred forecaster.

**Separate AIS layer.** The NOAA measurement code uses position, attributed zones, speed, persistence and maximum gaps to distinguish approach, transit, berth and anchorage candidates. Completed episodes are retrospective QA; a future berth visit cannot change an earlier queue label. Counts and bounded observed hours carry reception, censoring and geometry warnings. Current geometry and cargo broadcast categories limit interpretation. Pilot/full-year status is stated by the measurement receipt, not inferred from a polished map.

**Verification and decision.** An independently coded arithmetic check reproduced all 45 aggregate metric rows and the four primary bootstrap intervals from the immutable forecasts. It checked release clocks, target aggregation and serialized ridge predictions without retuning. That is a separate calculation by an AI agent, not independent human validation. I would retain the simpler benchmark, keep the measurement infrastructure, and require a genuinely prospective snapshot experiment before claiming operational value.

## Ten likely questions, with direct answers

1. **Why these three gateways?** They were fixed in the brief before outcome inspection and span major West/East Coast import gateways. They are not representative of every U.S. port. Their sum is deliberately a selected-gateway composite.

2. **Did geography add predictive value?** It reduced primary WAPE by 5.69% relative to aggregate shipping, but the intervals include zero and longer lags weaken it. More importantly, it lost to the validation-selected calls-to-TEU baseline. The rule's status is `PROMISING_BUT_UNCERTAIN`; the practical conclusion is not to prefer the geographic model.

3. **Is this point-in-time?** No. Observation dates and assumed release lags are not archived availability evidence. The inputs are current-vintage snapshots, and every official target's first-release timestamp is unknown. Verified historical lead time therefore has a zero eligible denominator.

4. **How was leakage controlled?** Only complete activity windows ending before the lagged cutoff are used; both numerator and seasonal denominator must be available for training growth. Scaling is train-only, penalties and comparator identities are validation-only, and the shared fallback prevents model-specific month selection. Future perturbation checks and receipts test these controls; they do not undo source revisions.

5. **Why can a simple conversion beat ridge?** TEU-per-call conversion expresses a stable operational relationship with fewer fitted degrees of freedom. It also uses gateway information, so it is a serious noncandidate benchmark, not a geography-free control. Vessel mix or monthly rate changes can still break it; this result is not a universal guarantee.

6. **Why WAPE and two block lengths?** WAPE weights absolute TEU error by actual composite throughput, preserving one common denominator. Paired blocks retain some monthly dependence. Three and six months were prespecified, with 10,000 draws each. With only 24 months, the intervals are limited descriptive evidence, not a substitute for a longer prospective record.

7. **How did you handle missing observations?** Required current/prior-year shipping windows must be complete. The primary common policy falls back to last year's same-month TEUs for all models on three origins. Missing receiver coverage or a missing source partition never becomes a confirmed zero queue. Complete-window conditional scores remain secondary.

8. **Does an anchored cargo vessel prove import congestion?** No. Cargo codes are not confirmed container identities; stops can have many causes. Geometry, continuity and censoring are explicit. The limited BTS operational waiting-stock comparison has different population, footprint and time-of-day definitions, so it is consistency evidence, not independent truth.

9. **What is actually reproducible?** The locked inputs, selections, forecasts, metric arithmetic, bootstrap and notebook outputs are hash-addressed and locally executable. Fresh downloads may be revised. Raw source snapshots are private by default under their terms, while limited transformed aggregates and source attribution can be inspected. Original code licensing does not relicense provider data.

10. **What would you do next?** Register and retain real publication-time snapshots, issue untouched day-21 forecasts prospectively, and compare the same simple baseline. Improve terminal/vessel validation under a separate declared measurement plan. Do not tune the current test sample until geography wins, and do not claim a trading or national-demand application without another study.

## Evidence to open during the conversation

- `artifacts/figures/benchmark_comparison.png`: strongest benchmark visible.
- `artifacts/figures/availability_sensitivity.png`: assumptions change the result.
- `artifacts/protocol_lock.json`: what was fixed before test performance inspection.
- `artifacts/audit/independent_research_audit.json`: actual numerical checks and their scope.
- `notebooks/01_measurement_audit.ipynb`: actual source coverage, bounded reconstruction and geometry limits.
- `notebooks/02_locked_research.ipynb`: package-imported metrics and paired bootstrap.

Do not describe the project as live, globally unseen, independently human-validated, or predictive of inflation or asset returns. Public PortWatch attribution: **Sources: Kpler; UN Global Platform; IMF PortWatch** ([source](https://portwatch.imf.org/)).
