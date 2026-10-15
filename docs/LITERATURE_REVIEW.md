# Bounded literature review: what this study does and does not add

Reviewed on 2026-10-15, before this source-review agent inspected any project forecast performance. The hypothesis is narrow: does retaining gateway identity in container-call features improve a selected-gateway loaded-import TEU nowcast beyond aggregate calls at the same cutoff? The separate measurement question concerns coverage-aware berth and anchorage candidates, not a long congestion forecasting history. Neither AIS nowcasting nor a busy-versus-congested distinction is new.

## S01 — Cerdeiro, Komaromi, Liu and Saeed (2020)

**World Seaborne Trade in Real Time: A Proof of Concept for Building AIS-based Nowcasts from Scratch.** IMF WP 20/57; DOI [10.5089/9781513544106.001](https://doi.org/10.5089/9781513544106.001). [Original publication](https://www.imf.org/en/publications/wp/issues/2020/05/14/world-seaborne-trade-in-real-time-a-proof-of-concept-for-building-ais-based-nowcasts-from-49393).

- **Question:** Can raw AIS broadcasts become policy-relevant trade indicators?
- **Data and method:** Vessel radio messages support port identification, port-to-port voyages and trade-volume estimates; the authors compare the resulting indicators with official country and global statistics.
- **Limitation:** Inferred trade depends on vessel characteristics and local port knowledge; fit to aggregate trade is not a guarantee for monthly loaded-import TEUs at an individual gateway.
- **Design implication:** Treat this as prior art. Separate observed calls from inferred tonnage and official container units. This project's contribution is a frozen incremental-information comparison and an auditable local implementation, not invention of AIS trade nowcasting.
- **Verification:** Original publisher abstract and metadata; detailed algorithm claims beyond that abstract are not asserted here.

## S02 — Komaromi, Cerdeiro and Liu (2022)

**Supply Chains and Port Congestion Around the World.** IMF WP 22/59; DOI [10.5089/9798400202957.001](https://doi.org/10.5089/9798400202957.001). [Original paper PDF](https://www.imf.org/-/media/files/publications/wp/2022/english/wpiea2022059-print-pdf.pdf).

- **Question:** How much did shipping delays change during the pandemic, and were they simply a consequence of higher throughput?
- **Data and method:** AIS-derived voyages and cargo estimates are used to compare international travel times, including destination turnaround, against pre-pandemic origin-destination benchmarks. The authors examine throughput and turnaround together.
- **Limitation:** Route-relative travel delay is not identical to observed anchorage time, and the presence of longer delays with lower throughput does not identify a particular local cause.
- **Design implication:** Keep flow and friction as separate axes. Slow or stationary ships are queue candidates until supported by zone, persistence and trajectory evidence. Do not call all activity congestion.
- **Verification:** Original PDF, introduction and Sections II-III, especially printed pages 4-7, reviewed through the browser reader. No paper-specific headline estimate is imported into this project's findings.

## S03 — Verschuur, Koks and Hall (2022)

**Ports' criticality in international trade and global supply-chains.** Nature Communications 13, 4351. [Original open-access article](https://www.nature.com/articles/s41467-022-32070-0), DOI 10.1038/s41467-022-32070-0.

- **Question:** Which ports are economically critical once hinterland and cross-border supply-chain links are considered?
- **Data and method:** The OxMarTrans maritime/hinterland trade-allocation model is linked to EORA multi-regional input-output tables; the study's base year is 2015. Port-level economic dependency is different from simple port throughput or shipping-network centrality.
- **Limitation:** Modeled network allocation and industry-level input-output relationships are not observations of a named company's exact shipment exposure. Model vintage also differs from this project's 2019–2025 activity panel.
- **Design implication:** Do not map listed-company exposure from headquarters proximity. The v1 analyst-use case concerns goods flows and information timing, not security-specific earnings or investment returns.
- **Verification:** Original article abstract, introduction, model/data description and results framework were inspected.

## S04 — Arslanalp and coauthors (2025)

**Nowcasting Global Trade from Space.** IMF WP 25/93; DOI [10.5089/9798229009294.001](https://doi.org/10.5089/9798229009294.001). [Original publication](https://www.imf.org/en/publications/wp/issues/2025/05/16/nowcasting-global-trade-from-space-566957).

- **Question:** Can satellite-based vessel movements provide timely global and regional trade estimates?
- **Data and method:** PortWatch port-level inputs are transformed in a statistical-compilation sequence that estimates customs values, constructs import/export deflators and then estimates trade volumes.
- **Limitation:** Weight-based shipping estimates, value-based trade and deflated economic volumes are distinct concepts. Success at global/regional aggregation does not establish the present gateway-level loaded-import TEU hypothesis.
- **Design implication:** Use container-specific call counts as the frozen primary activity input, maintain exact units and target definitions, and make geographic disaggregation earn its place against aggregate and released-target baselines.
- **Verification:** Original publisher abstract/summary and bibliographic record. The linked original PDF resolves in the browser catalog, but subsequent full-text access was rate-limited; no detailed appendix or numerical performance claims are asserted.

## S05 — Arslanalp, Exton, Gao, Saraiva, Kamali, Sozzi and Verschuur (2026)

**Nowcasting Country-Level Trade Estimates Using IMF PortWatch.** IMF WP 26/99, published May 22, 2026; DOI [10.5089/9798229046893.001](https://doi.org/10.5089/9798229046893.001). [Original publication](https://www.imf.org/en/publications/wp/issues/2026/05/19/nowcasting-country-level-trade-estimates-using-imf-portwatch-576176).

- **Question:** Can PortWatch support timely country trade estimates that compare credibly with official statistics?
- **Data and method:** The paper applies vessel-movement-based nowcasting to country trade and validates an initial group including Brazil, Jamaica, Japan, Samoa and the United States. It discusses complementary information and a US-import application.
- **Limitation:** Country performance and a published release workflow do not establish the historical publication date of the specific revised PortWatch rows acquired for this project.
- **Design implication:** Retain a narrower gateway-composite question and explicit current-vintage pseudo-real-time status. An assumed seven-day lag is not a verified historical vintage or a reproduction of the paper's release process.
- **Verification:** Original publisher abstract and metadata. Full-PDF follow-up was blocked/rate-limited, so no unverified model details or country-specific performance figures are repeated.

## S06 — Jiao, Lan, Liu and Zhao (2026)

**From Ports to Prices: The Inflationary Effects of Global Supply Chain Disruptions.** IMF WP 26/26, February 13, 2026; DOI [10.5089/9798229039284.001](https://doi.org/10.5089/9798229039284.001). [Original publication](https://www.imf.org/en/publications/wp/issues/2026/02/13/from-ports-to-prices-the-inflationary-effects-of-global-supply-chain-disruptions-573975).

- **Question:** How do shipping delays transmit to goods prices?
- **Data and method:** AIS-derived port-to-port shipping times are linked to granular trade and item-level prices. Cross-product differences in delay exposure are used to estimate average and dynamic price effects.
- **Limitation:** Such exposure mappings and identification assumptions are additional economic evidence; they are not supplied by this project's three gateways or by detecting stationary vessel candidates.
- **Design implication:** An analyst can investigate inventory timing or possible delivery friction, but no inflation coefficient, causal effect, earnings impact or equity alpha should be inferred from this measurement/nowcast exercise alone.
- **Verification:** Original publisher abstract and bibliographic metadata. Full-text follow-up was blocked/rate-limited; its numerical inflation estimate is deliberately not used.

## S07 — Benigno, di Giovanni, Groen and Noble (2022)

**The GSCPI: A New Barometer of Global Supply Chain Pressures.** New York Fed Staff Report 1017. [Original paper](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr1017.pdf); [index context](https://www.newyorkfed.org/research/policy/gscpi).

- **Question:** Can common pressures across international transport and manufacturing be summarized in a broad global indicator?
- **Data and method:** Transport costs and manufacturing PMI components from seven economies are adjusted using demand proxies, then summarized by principal components. Local projections examine inflation responses. The paper explicitly discusses imputation and historical revisions.
- **Limitation:** Demand removal is imperfect, the index is broader than maritime gateway activity, and current historical values can differ from earlier vintages.
- **Design implication:** Present GSCPI as context, not an interchangeable target or a comparator casually inserted after results. The three-gateway flow and short raw-AIS friction measures do not replace a global supply-chain index. Preserve vintages for any future historical GSCPI predictor.
- **Verification:** Original full PDF downloaded and reviewed, Sections 2–4, including index construction and vintage discussion.

## Synthesis and evidence boundary

The literature establishes AIS trade monitoring, delay measurement, economic-network exposure and broader pressure indicators. It does **not** answer this project's fixed incremental gateway-information test. The study therefore predeclares its target, container-call features, training-only transformations, same-cutoff baselines, temporal selection/test split, uncertainty procedure and claim gates. The geospatial contribution is independently useful only if its raw data, geometry, coverage, state logic and audits are real and traceable.

This is a bounded seven-source review, not a systematic review or a replication of these papers. Three original full-text sources were inspected; four IMF entries are explicitly abstract-level checks after bounded HTTP 403/429 failures. Material claims above for those entries are restricted to what their original publication abstracts establish. Detailed identification/robustness appraisal of those four papers remains a documented literature limitation. No evidence from these papers is reported as this project's empirical result.
