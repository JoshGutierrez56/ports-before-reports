"""Official loaded-import monthly TEUs from BTS, with non-substitution guards."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
import pandas as pd
from .operational import fetch_json

URL="https://data.bts.gov/resource/y5ut-ibwt.json"
INDICATOR="Loaded Import Containers at Select U.S. Ports in TEUs"
PORTS={"Los Angeles":("los_angeles","san_pedro_bay"),"Long Beach":("long_beach","san_pedro_bay"),"NY-NJ":("new_york_new_jersey","new_york_new_jersey"),"Savannah":("savannah","savannah")}
WHERE="indicator = 'Loaded Import Containers at Select U.S. Ports in TEUs' AND measure1 IN ('Los Angeles','Long Beach','NY-NJ','Savannah') AND date >= '2019-01-01T00:00:00' AND date < '2026-01-01T00:00:00'"


def parse_bts(rows: list[dict], snapshot_id: str) -> pd.DataFrame:
    frame=pd.DataFrame(rows)
    required={"id","date","indicator","measure1","value1","units","source"}
    if not required.issubset(frame):raise ValueError(f"BTS schema missing {required-set(frame)}")
    if not frame.indicator.eq(INDICATOR).all() or not frame.units.eq("TEUs").all():
        raise ValueError("Only documented loaded import TEUs are admissible; totals/tons rejected")
    if not set(frame.measure1).issubset(PORTS):raise ValueError("Unknown port scope")
    frame["month"]=pd.to_datetime(frame.date).dt.to_period("M").dt.to_timestamp()
    if frame.duplicated(["measure1","month"]).any():raise ValueError("Duplicate/revised target month: select a documented vintage, do not sum revisions")
    frame["teu"]=pd.to_numeric(frame.value1,errors="raise")
    if frame.teu.isna().any() or (frame.teu<0).any():raise ValueError("Invalid official TEU value")
    frame["official_port_id"]=frame.measure1.map(lambda p:PORTS[p][0])
    frame["gateway_id"]=frame.measure1.map(lambda p:PORTS[p][1])
    frame["direction"]="import"
    frame["load_status"]="loaded"
    frame["reporting_calendar"]="calendar_month"
    frame["first_release_at_utc"]=pd.NaT
    frame["revision_at_utc"]=pd.NaT
    frame["vintage_id"]=snapshot_id
    frame["snapshot_id"]=snapshot_id
    frame["source_url"]=URL
    frame["quality_flags"]="current_vintage_first_release_unknown"
    return frame.sort_values(["official_port_id","month"]).reset_index(drop=True)


def acquire_targets(root: str | Path) -> dict:
    root=Path(root)
    metadata=json.loads((root/"data/manifests/source_snapshots/bts_freight_indicators/metadata.json").read_text())
    if metadata.get("id")!="y5ut-ibwt":raise ValueError("Wrong BTS dataset")
    terms=metadata.get("license",{}).get("termsLink")
    before,_=fetch_json(root,"bts_freight_indicators",URL,"target_count_before.json",params={"$where":WHERE,"$select":"count(*)"},terms_url=terms)
    expected=int(before[0]["count"])
    rows=[];receipts=[]
    for offset in range(0,expected,500):
        batch,receipt=fetch_json(root,"bts_freight_indicators",URL,f"targets_{offset:05d}.json",params={"$where":WHERE,"$order":"id ASC","$limit":500,"$offset":offset},terms_url=terms)
        rows.extend(batch);receipts.append(receipt)
    after,_=fetch_json(root,"bts_freight_indicators",URL,"target_count_after.json",params={"$where":WHERE,"$select":"count(*)"},terms_url=terms)
    if before!=after or len(rows)!=expected or len({r['id'] for r in rows})!=expected:raise ValueError("BTS count/unique-ID reconciliation failed")
    digest=hashlib.sha256("".join(r["sha256"] for r in receipts).encode()).hexdigest()
    snapshot_id="bts-target-panel-"+digest[:16]
    frame=parse_bts(rows,snapshot_id)
    frame["verified_available_at_utc"]=pd.to_datetime(max(r["retrieved_at_utc"] for r in receipts),utc=True)
    directory=root/"data/curated";directory.mkdir(parents=True,exist_ok=True)
    frame.to_parquet(directory/"official_teu_monthly.parquet",index=False)
    coverage=frame.groupby("official_port_id").agg(months=("month","size"),first=("month","min"),last=("month","max")).reset_index()
    coverage.to_csv(root/"data/manifests/source_target_coverage.csv",index=False)
    expected_grid=pd.MultiIndex.from_product([list(PORTS),pd.date_range('2019-01-01','2025-12-01',freq='MS')],names=['measure1','month'])
    missing=expected_grid.difference(pd.MultiIndex.from_frame(frame[['measure1','month']]))
    receipt={"status":"complete" if len(missing)==0 else "incomplete", "row_count":len(frame),"expected_rows":336,"missing_port_months":[[a,str(b.date())] for a,b in missing],"snapshot_id":snapshot_id,"source_snapshot_ids":[r["snapshot_id"] for r in receipts],"first_release_known_count":0,"path":"data/curated/official_teu_monthly.parquet","sha256":hashlib.sha256((directory/"official_teu_monthly.parquet").read_bytes()).hexdigest(),"schema_hash":hashlib.sha256(json.dumps([(c,str(t)) for c,t in frame.dtypes.items()]).encode()).hexdigest()}
    (root/"data/manifests/source_targets.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    return receipt


def parse_la_html(path: str | Path, year: int) -> tuple[pd.DataFrame, float]:
    """Require source table headers; fiscal totals and total imports are excluded."""
    tables=pd.read_html(Path(path))
    matches=[t for t in tables if "Loaded Imports" in t.astype(str).to_numpy()]
    if len(matches)!=1:raise ValueError("LA exact Loaded Imports header absent or ambiguous")
    table=matches[0]
    header=table.iloc[0].astype(str).tolist()
    column=header.index("Loaded Imports")
    if "Total TEUs" not in header or "Empty Imports" not in header:raise ValueError("LA units/direction/load headers incomplete")
    rows=[]
    for _,record in table.iloc[1:].iterrows():
        label=str(record.iloc[0])
        try: month=pd.to_datetime(f"{label} {year}",format="%B %Y")
        except ValueError:continue
        rows.append({"official_port_id":"los_angeles","month":month,"authority_teu":float(str(record.iloc[column]).replace(",",""))})
    annual=table[table.iloc[:,0].astype(str).str.contains("Calendar Year",case=False)]
    if len(rows)!=12 or len(annual)!=1:raise ValueError("LA monthly/calendar annual table incomplete")
    return pd.DataFrame(rows),float(str(annual.iloc[0,column]).replace(",",""))


def parse_savannah_pdf(path: str | Path) -> tuple[pd.DataFrame,pd.DataFrame]:
    """Parse inspected GPA Savannah Import Full rows, never statewide/fiscal totals."""
    from pypdf import PdfReader
    reader=PdfReader(str(path));rows=[];annual=[]
    for page_number,page in enumerate(reader.pages):
        text=page.extract_text()
        if "Port of Savannah" not in text or "TEU Total for All Terminals" not in text:
            raise ValueError("Savannah PDF reporting perimeter/TEU header not established")
        for match in re.finditer(r"(20\d\d)\s+Import Full\s+((?:[\d,]+\s+){12}[\d,]+)",text):
            year=int(match.group(1))
            if not 2019<=year<=2025:continue
            nums=[int(n.replace(",","")) for n in match.group(2).split()]
            if len(nums)!=13:raise ValueError("Savannah expected twelve calendar months plus annual total")
            rows.extend({"official_port_id":"savannah","month":pd.Timestamp(year,m+1,1),"authority_teu":nums[m],"pdf_page":page_number+1} for m in range(12))
            annual.append({"official_port_id":"savannah","year":year,"annual_authority_teu":nums[12],"monthly_authority_sum":sum(nums[:12]),"pdf_page":page_number+1})
    if len(rows)!=84:raise ValueError(f"Savannah import full rows incomplete: {len(rows)}")
    return pd.DataFrame(rows),pd.DataFrame(annual)


def crosscheck_targets(root: str | Path) -> dict:
    root=Path(root);snapshot=root/"data/manifests/source_snapshots"
    target=pd.read_parquet(root/"data/curated/official_teu_monthly.parquet")
    checks=[];annual=[]
    for year in [2019,2025]:
        rows,total=parse_la_html(snapshot/"la"/f"{year}.html",year)
        rows["source_url"]=f"https://portoflosangeles.org/business/statistics/container-statistics/historical-teu-statistics-{year}"
        checks.append(rows)
        annual.append({"official_port_id":"los_angeles","year":year,"annual_authority_teu":total,"monthly_authority_sum":float(rows.authority_teu.sum())})
    sav,sav_annual=parse_savannah_pdf(snapshot/"savannah/monthly_dec2025.pdf")
    sav["source_url"]="https://gaports.com/wp-content/uploads/2026/02/Monthly-TEU-Throughput-December-2025.pdf"
    checks.append(sav);annual.extend(sav_annual.to_dict("records"))
    check=pd.concat(checks,ignore_index=True).merge(target[["official_port_id","month","teu"]],on=["official_port_id","month"],validate="one_to_one")
    check["difference_teu"]=check.teu-check.authority_teu
    check["comparison_status"]=check.difference_teu.abs().map(lambda n:"matches_within_one_teu_rounding" if n<=1 else "current_vintage_difference_requires_disclosure")
    check.to_csv(root/"data/manifests/source_target_crosschecks.csv",index=False)
    # Page 3 (printed pp4-5) visually inspected: TEUs / Imports / LOADS / 2019, not total imports.
    annual.append({"official_port_id":"new_york_new_jersey","year":2019,"annual_authority_teu":3770971.,"monthly_authority_sum":None,"pdf_page":3})
    annual=pd.DataFrame(annual)
    target["year"]=target.month.dt.year
    sums=target.groupby(["official_port_id","year"]).teu.sum().rename("bts_monthly_sum").reset_index()
    annual=annual.merge(sums,on=["official_port_id","year"],validate="one_to_one")
    annual["bts_minus_authority"]=annual.bts_monthly_sum-annual.annual_authority_teu
    annual["authority_rounding_residual"]=annual.monthly_authority_sum-annual.annual_authority_teu
    annual.to_csv(root/"data/manifests/source_target_annual_reconciliation.csv",index=False)
    receipt={"monthly_crosschecks":len(check),"monthly_within_one_teu":int(check.difference_teu.abs().le(1).sum()),"monthly_max_abs_difference_teu":float(check.difference_teu.abs().max()),"annual_crosschecks":len(annual),"long_beach":"authority_archive_403_not_bypassed_BTS_series_definition_verified","canonical_targets_changed":False,"reviewer":"agent_source_headers_and_pdf_page_images"}
    (root/"data/manifests/source_target_crosscheck_receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    return receipt
