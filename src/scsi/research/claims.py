"""Headline gates implement the supplied decision rule; no synthetic fallback."""
def classify(comparisons,critical_leakage=False,robustness_undermines=False):
    direct=next(c for c in comparisons if c["comparator"]=="aggregate_activity_ridge")
    if critical_leakage:return "REAL_DATA_BLOCKED"
    if direct["relative_lift"]<=0:return "NO_INCREMENTAL_LIFT"
    supported=all(c["relative_lift"]>=.05 and c["n_months"]>=20 and len(c["bootstrap"])==2 and all(b["lower"] is not None and b["lower"]>0 for b in c["bootstrap"]) for c in comparisons)
    return "HISTORICAL_LIFT_SUPPORTED" if supported and not robustness_undermines else "PROMISING_BUT_UNCERTAIN"
