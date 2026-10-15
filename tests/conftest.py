import numpy as np
import pandas as pd
import pytest
from scsi.config import GATEWAYS

@pytest.fixture
def synthetic_flow():
    days=pd.date_range("2019-01-01","2025-12-31",freq="D")
    rows=[]
    for j,g in enumerate(GATEWAYS):
        for i,d in enumerate(days):
            rows.append({"gateway_id":g,"source_port_id":f"synthetic_{j}","observation_date":d,"vessel_category":"container","port_calls":float(7+j+(i%13))})
    return pd.DataFrame(rows)

@pytest.fixture
def synthetic_targets():
    rows=[]
    for i,m in enumerate(pd.date_range("2019-01-01","2025-12-01",freq="MS")):
        for j,(port,gateway) in enumerate([("la","san_pedro_bay"),("lb","san_pedro_bay"),("ny","new_york_new_jersey"),("sv","savannah")]):
            rows.append({"official_port_id":port,"gateway_id":gateway,"month":m,"direction":"import","load_status":"loaded","teu":100000+20000*j+250*i+1000*np.sin(i),"first_release_at_utc":None,"unit":"TEU"})
    return pd.DataFrame(rows)
