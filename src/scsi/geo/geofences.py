"""Attributed candidate zones; authoritative anchorages and interpreted berth corridors."""
from __future__ import annotations
import json
from pathlib import Path
import urllib.parse
import numpy as np
from pyproj import CRS, Transformer
import shapely
from shapely.geometry import shape, mapping, LineString, Polygon, Point, box
from shapely.ops import transform, unary_union
from scsi.sources.noaa_points import BBOXES, _request, digest, ledger, utcnow

ANCHOR_SERVICE = "https://coast.noaa.gov/arcgis/rest/services/OceanReports/DesignatedAnchorageAreas/MapServer/0"
LOCAL_CRS = {"san_pedro_bay": "EPSG:32611", "new_york_new_jersey": "EPSG:32618", "savannah": "EPSG:32617"}
PILOTS = {"san_pedro_bay": "https://nauticalcharts.noaa.gov/publications/coast-pilot/files/cp7/CPB7_C04_WEB.pdf", "new_york_new_jersey": "https://nauticalcharts.noaa.gov/publications/coast-pilot/files/cp2/CPB2_C11_WEB.pdf", "savannah": "https://nauticalcharts.noaa.gov/publications/coast-pilot/files/cp4/CPB4_C07_WEB.pdf"}

def meter_buffer(geometry, meters, projected_crs):
    crs = CRS.from_user_input(projected_crs)
    if not crs.is_projected or not all(a.unit_name.lower() in ("metre", "meter") for a in crs.axis_info):
        raise ValueError("Buffer CRS must be projected with meter units, never longitude/latitude degrees")
    forward = Transformer.from_crs(4326, crs, always_xy=True).transform
    backward = Transformer.from_crs(crs, 4326, always_xy=True).transform
    return transform(backward, transform(forward, geometry).buffer(meters))

# Quay-centerline interpretations, NOT legal/surveyed terminal boundaries. Coordinates
# located from the cited Coast Pilot facility descriptions and port terminal layouts.
# Width 150m admits ship centers beside the quay; buffers are tested separately.
BERTH_LINES = {
 "san_pedro_bay": [
  ("LA APM Pier 400", [(-118.249,33.720),(-118.243,33.735),(-118.239,33.739)]),
  ("LA Fenix Pier 300", [(-118.232,33.733),(-118.230,33.744)]),
  ("LA Everport", [(-118.235,33.751),(-118.241,33.757)]),
  ("LA Yusen", [(-118.254,33.749),(-118.263,33.755)]),
  ("LA TraPac", [(-118.267,33.765),(-118.251,33.765)]),
  ("LA West Basin", [(-118.278,33.755),(-118.278,33.768)]),
  ("LB Pier J", [(-118.190,33.739),(-118.180,33.746),(-118.176,33.751)]),
  ("LB Pier G", [(-118.201,33.753),(-118.194,33.759)]),
  ("LB Pier E", [(-118.216,33.753),(-118.217,33.766)]),
  ("LB Pier T", [(-118.234,33.754),(-118.236,33.768)]),
  ("LB Pier A", [(-118.204,33.773),(-118.204,33.783)]),
  ("LB Pier C", [(-118.212,33.770),(-118.212,33.779)])],
 "new_york_new_jersey": [
  ("Port Newark south quay", [(-74.151,40.674),(-74.139,40.674)]),
  ("Port Elizabeth north quay", [(-74.159,40.670),(-74.144,40.670)]),
  ("Port Elizabeth east quay", [(-74.141,40.670),(-74.143,40.658)]),
  ("Port Jersey Bayonne", [(-74.087,40.662),(-74.073,40.666)]),
  ("Howland Hook", [(-74.182,40.644),(-74.180,40.638)]),
  ("Red Hook", [(-74.014,40.683),(-74.017,40.679)])],
 "savannah": [("Garden City container berths 1-6", [(-81.1330,32.1150),(-81.1345,32.1230),(-81.1390,32.1325)]),
              ("Garden City northern container berths", [(-81.1390,32.1325),(-81.1450,32.1425)])]
}
TRANSIT_LINES = {
 "san_pedro_bay": [[(-118.2517,33.7086),(-118.272,33.738),(-118.267,33.755)], [(-118.184,33.721),(-118.207,33.745),(-118.224,33.752)]],
 "new_york_new_jersey": [[(-74.045,40.590),(-74.041,40.633),(-74.054,40.664),(-74.061,40.688)], [(-74.140,40.641),(-74.132,40.667),(-74.127,40.696)]],
 "savannah": [[(-80.7194,31.9644),(-80.816,32.022),(-80.916,32.034),(-80.985,32.055),(-81.062,32.082),(-81.107,32.101),(-81.129,32.122),(-81.137,32.137)]]
}

def build_geofences(root, config=None):
    root = Path(root)
    output = root / "data/geography/geofences_v1.geojson"
    if output.exists():
        return json.loads(output.read_text())
    output.parent.mkdir(parents=True, exist_ok=True)
    features, sources = [], []
    for gateway, bbox in BBOXES.items():
        params = dict(f="geojson", where="1=1", geometry=",".join(map(str,bbox)), geometryType="esriGeometryEnvelope", inSR=4326, outSR=4326, spatialRel="esriSpatialRelIntersects", outFields="*", orderByFields="OBJECTID")
        url = ANCHOR_SERVICE + "/query?" + urllib.parse.urlencode(params)
        with _request(url) as r:
            body = r.read(10 * 1024 * 1024)
        data = json.loads(body)
        if data.get("exceededTransferLimit") or data.get("error"):
            raise ValueError("NOAA anchorage extraction incomplete")
        source = root / f"data/geography/geofences_source_{gateway}.geojson"
        source.write_bytes(body)
        ledger(root, "anchorage_geometry_acquired", gateway_id=gateway, url=url, network_bytes=len(body), sha256=digest(source))
        # Spatial API count reconciliation, not a preview assumed complete.
        countparams = {**params, "f":"json", "returnCountOnly":"true"}
        countparams.pop("orderByFields",None)
        with _request(ANCHOR_SERVICE+"/query?"+urllib.parse.urlencode(countparams)) as r:
            countbody=r.read(); count=json.loads(countbody)["count"]
        ledger(root,"anchorage_geometry_count",network_bytes=len(countbody),gateway_id=gateway,count=count)
        if len(data.get("features",[])) != count:
            raise ValueError("Anchorage server count mismatch")
        sources.append(dict(gateway_id=gateway,url=url,sha256=digest(source),source_count=count,license="US federal source; attributed NOAA/USCG",retrieved_at_utc=utcnow()))
        for feature in data.get("features", []):
            props = feature["properties"]
            name, cfr = props.get("name", ""), props.get("CFR", "")
            include = (gateway == "san_pedro_bay" and cfr == "33 CFR 110.214" and "Naval" not in name and ("Commercial" in name or "General" in name)) or (gateway == "new_york_new_jersey" and cfr == "33 CFR 110.155")
            if include:
                geom=shape(feature["geometry"]).intersection(box(*bbox))
                if not geom.is_empty:
                    features.append(dict(type="Feature",geometry=mapping(geom),properties=dict(gateway_id=gateway,zone="anchorage",name=name,source_url=ANCHOR_SERVICE,source_object_id=props["OBJECTID"],cfr=cfr,geometry_basis="NOAA designated anchorage; current-vintage, not verified 2024 geometry")))
        # Outer polygon is explicitly only an approach/acquisition area, never queue.
        features.append(dict(type="Feature",geometry=mapping(box(*bbox)),properties=dict(gateway_id=gateway,zone="approach",name="Acquisition / approach envelope",geometry_basis="Analyst envelope; not harbor or anchorage boundary")))
        for name, line in BERTH_LINES[gateway]:
            features.append(dict(type="Feature",geometry=mapping(meter_buffer(LineString(line),150,LOCAL_CRS[gateway])),properties=dict(gateway_id=gateway,zone="container_berth",name=name,source_url=PILOTS[gateway],geometry_basis="Analyst-interpreted quay corridor, 150m half-width; approximate, not official boundary")))
        for i, line in enumerate(TRANSIT_LINES[gateway]):
            features.append(dict(type="Feature",geometry=mapping(meter_buffer(LineString(line),180,LOCAL_CRS[gateway])),properties=dict(gateway_id=gateway,zone="transit",name=f"Approach channel interpretation {i+1}",source_url=PILOTS[gateway],geometry_basis="Analyst-interpreted channel centerline with 180m half-width")))
    # Coast Pilot 4 ch7 para143: north/NE of Tybee buoy, outside a two-nautical-mile radius.
    # This is an interpreted bounded holding-candidate area, NOT designated anchorage.
    buoy=Point(-80-43/60-10/3600,31+57/60+52/3600)
    sector=Polygon([(-80.76,31.97),(-80.68,32.035),(-80.65,32.12),(-80.80,32.12),(-80.82,32.035)])
    geom=sector.difference(meter_buffer(buoy,3704,LOCAL_CRS["savannah"]))
    features.append(dict(type="Feature",geometry=mapping(geom),properties=dict(gateway_id="savannah",zone="anchorage",name="Tybee north/northeast holding candidate",source_url=PILOTS["savannah"],geometry_basis="Analyst sector interpreting Coast Pilot4 chapter7 paragraph143; excludes two-nautical-mile buoy radius; no river anchorage inferred")))
    result=dict(type="FeatureCollection",metadata=dict(version="scsi-geofences-v1",created_at_utc=utcnow(),crs="EPSG:4326",local_projected_crs=LOCAL_CRS,review="Agent-assisted, not independent hydrographic validation",limitations="Current geometry vintage; approximate berth/channel corridors; cargo class is not containership identity; coastal acquisition bounds truncate distant anchorage"),features=features)
    output.write_text(json.dumps(result),encoding="utf8")
    (root/"data/geography/geofences_provenance.json").write_text(json.dumps(dict(sources=sources,geometry_sha256=digest(output),coast_pilot_sources=PILOTS,method=result["metadata"],terminal_interpretations=BERTH_LINES),indent=2),encoding="utf8")
    return result

def classify_zones(points, geofences, buffer_meters=0):
    """Assign exactly one zone. Transit channels override anchorages; berths win."""
    result=np.full(len(points),"approach",dtype=object)
    for gateway in BBOXES:
        loc=np.flatnonzero(points.gateway_id.to_numpy()==gateway)
        if not len(loc): continue
        xy=shapely.points(points.longitude.to_numpy()[loc],points.latitude.to_numpy()[loc])
        for zone in ("anchorage","transit","container_berth","other_commercial_berth"):
            geoms=[shape(f["geometry"]) for f in geofences["features"] if f["properties"].get("gateway_id")==gateway and f["properties"].get("zone")==zone]
            if not geoms: continue
            union=unary_union(geoms)
            if buffer_meters and zone in ("anchorage","container_berth","other_commercial_berth"):
                union=meter_buffer(union,buffer_meters,LOCAL_CRS[gateway])
            shapely.prepare(union)
            result[loc[shapely.intersects(union,xy)]]=zone
    return result

def refine_pilot_geofences(root):
    """One documented pilot correction: surveyed ENC outlines replace hand locators.

    Only available before the immutable pilot lock; no future-year positions or
    forecast outcomes are inputs. ENC feature types are not trusted as container
    labels: named facilities are reconciled with Coast Pilot descriptions.
    """
    root=Path(root)
    if (root/"artifacts/audit/geo_pilot_freeze.json").exists():raise RuntimeError("Geometry frozen")
    output=root/"data/geography/geofences_v1.geojson"
    data=json.loads(output.read_text())
    if data.get("metadata",{}).get("pilot_enc_refinement"):return data
    (root/"data/geography/geofences_pilot_initial.geojson").write_bytes(output.read_bytes())
    # Artificial quay edges are absent from some ENC coastline records. Retain
    # the explicitly interpreted LA/Savannah locators as candidate corridors;
    # replace NY named terminals with actual facility outlines, retaining RedHook.
    data["features"]=[f for f in data["features"] if f["properties"].get("zone")!="container_berth" or f["properties"].get("gateway_id")!="new_york_new_jersey" or f["properties"].get("name")=="Red Hook"]
    encbase="https://encdirect.noaa.gov/arcgis/rest/services/encdirect/enc_harbour/MapServer"
    refs=[]
    for gateway,suffix,expected in [("san_pedro_bay","san_pedro_bay",133),("savannah","savannah_terminal",52)]:
        source=root/f"data/geography/geofences_enc_84_{suffix}.geojson";reference=json.loads(source.read_text())
        if reference.get("exceededTransferLimit") or len(reference["features"])!=expected:raise ValueError("Incomplete ENC coastline reference")
        coastline=unary_union([shape(f["geometry"]) for f in reference["features"]])
        for name,line in BERTH_LINES[gateway]:
            locator=meter_buffer(LineString(line),600,LOCAL_CRS[gateway])
            selected=coastline.intersection(locator)
            if selected.is_empty:continue
            geom=meter_buffer(selected,150,LOCAL_CRS[gateway])
            data["features"].append(dict(type="Feature",geometry=mapping(geom),properties=dict(gateway_id=gateway,zone="container_berth",name=name,source_url=encbase+"/84",facility_reference_url=PILOTS[gateway],geometry_basis="NOAA ENC coastline clipped within600m of CoastPilot-attributed terminal locator, then150m meter buffer. Candidate functional attribution, not surveyed terminal ownership.")))
        refs.append(dict(path=source.name,sha256=digest(source),source_url=encbase+"/84",server_count=expected))
    source=root/"data/geography/geofences_enc_179_new_york_new_jersey.geojson";reference=json.loads(source.read_text())
    if len(reference["features"])!=5:raise ValueError("Incomplete ENC facility reference")
    names={"Port Elizabeth Marine Terminal","Global Marine Terminal","New York Container Terminal","Port Newark Marine Terminal"}
    for feature in reference["features"]:
        pr=feature["properties"];name=pr.get("OBJNAM")
        if name not in names:continue
        # ENC CATHAF calls named container facilities ferry/yacht terminals. We
        # explicitly reject that semantic field and use official facility text.
        zone="other_commercial_berth" if name=="Port Newark Marine Terminal" else "container_berth"
        geom=meter_buffer(shape(feature["geometry"]).boundary,150,LOCAL_CRS["new_york_new_jersey"])
        data["features"].append(dict(type="Feature",geometry=mapping(geom),properties=dict(gateway_id="new_york_new_jersey",zone=zone,name=name,source_url=encbase+"/179",source_object_id=pr.get("HARBOUR.HRBFAC_POLYGON.FID"),source_chart=pr.get("DSNM"),source_date=pr.get("SORDAT"),facility_reference_url=PILOTS["new_york_new_jersey"],geometry_basis="150m corridor around NOAA ENC named facility perimeter; functional class from CoastPilot, not erroneous ENC CATHAF; source-vintage expansion limits apply")))
    refs.append(dict(path=source.name,sha256=digest(source),source_url=encbase+"/179",server_count=5))
    data["metadata"].update(pilot_enc_refinement=True,refinement_basis="January pilot visual audit found hand-locator undercoverage; supplemented LA/Savannah interpreted corridors with NOAA ENC outlines and replaced NY named terminals with actual facility outlines, without changing speed/gap/persistence or forecast design",enc_sources=refs,limitations="Current geometry vintage and source-chart age; candidate functional berth attribution; incomplete ENC artificial-quay coverage, interpreted corridors retained; coarse channel interpretations; offshore acquisition truncation. High geometry sensitivity is reported, not hidden.")
    output.write_text(json.dumps(data),encoding="utf8")
    prov=root/"data/geography/geofences_provenance.json";pr=json.loads(prov.read_text());pr.update(geometry_sha256=digest(output),enc_refinement=refs,refinement=data["metadata"]["refinement_basis"]);prov.write_text(json.dumps(pr,indent=2),encoding="utf8")
    ledger(root,"pilot_geometry_refinement",geometry_sha256=digest(output),basis=data["metadata"]["refinement_basis"],enc_sources=refs)
    return data
