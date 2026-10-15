"""Publication figures are drawn from frozen observed outcomes/predictions only."""
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

NAMES={"seasonal_naive":"Last year's month","released_target_ridge":"Released target history","aggregate_activity_ridge":"Aggregate shipping","geography_ridge":"Geographic shipping","simple_calls_to_teu":"Calls-to-TEU benchmark"}
COLORS={"geography_ridge":"#2558d5","aggregate_activity_ridge":"#679297","simple_calls_to_teu":"#ae7122","seasonal_naive":"#8a91a1","released_target_ridge":"#7a68a0"}

def create_figures(root,results):
    root=Path(root);out=root/"artifacts/figures";out.mkdir(parents=True,exist_ok=True)
    primary=next(x for x in results["experiments"] if x["role"]=="primary")
    records=pd.DataFrame(json.loads((root/primary["prediction_artifact"]).read_text()))
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":11,"axes.spines.top":False,"axes.spines.right":False,"figure.facecolor":"#f5f7fb","axes.facecolor":"#f5f7fb","text.color":"#172742","axes.labelcolor":"#172742","xtick.color":"#526176","ytick.color":"#526176","savefig.facecolor":"#f5f7fb"})
    fig,ax=plt.subplots(figsize=(11,5.6),layout="constrained")
    actual=records.drop_duplicates("target_month").sort_values("target_month")
    ax.plot(pd.to_datetime(actual.target_month),actual.actual_teu/1e6,color="#172742",label="Official loaded imports",lw=2.7)
    for model in dict.fromkeys(["geography_ridge","aggregate_activity_ridge",primary["selected_benchmark"]]):
        d=records[records.model_id.eq(model)].sort_values("target_month")
        ax.plot(pd.to_datetime(d.target_month),d.prediction_teu/1e6,color=COLORS[model],label=NAMES[model],lw=1.8,ls="--" if model=="aggregate_activity_ridge" else "-")
    ax.set_title("What the models actually forecast",loc="left",fontweight="bold",fontsize=19,pad=18)
    ax.set_ylabel("Selected-gateway loaded imports · million TEUs")
    ax.grid(axis="y",alpha=.15);ax.legend(loc="lower left",ncol=2,fontsize=9,frameon=False)
    fig.supxlabel("2024–2025 · Day-21 historical nowcasts · assumed 7-day shipping / 60-day target lag",fontsize=9)
    fig.savefig(out/"actual_vs_predicted.png",dpi=170);fig.savefig(out/"actual_vs_predicted.svg");plt.close(fig)
    frame=pd.DataFrame(primary["metrics"])
    fig,ax=plt.subplots(figsize=(10,5.3),layout="constrained")
    order=["seasonal_naive","released_target_ridge","aggregate_activity_ridge","geography_ridge","simple_calls_to_teu"]
    vals=[float(frame.set_index("model_id").loc[m,"wape"])*100 for m in order]
    bars=ax.barh([NAMES[m] for m in order],vals,color=[COLORS[m] for m in order],height=.62)
    ax.bar_label(bars,labels=[f"{v:.2f}%" for v in vals],padding=7,fontsize=11)
    ax.set_xlim(0,max(vals)*1.23);ax.invert_yaxis();ax.set_xlabel("WAPE · percent · lower is better")
    winner=frame.sort_values("wape").iloc[0].model_id
    ax.set_title(f"{NAMES[winner]} had the lowest error",loc="left",fontweight="bold",fontsize=17,pad=18)
    fig.supxlabel("Same 24 test months and fallback policy · benchmark selected on 2023 validation",fontsize=9)
    fig.savefig(out/"benchmark_comparison.png",dpi=170);fig.savefig(out/"benchmark_comparison.svg");plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5.5),layout="constrained")
    for release,marker in [(60,"o"),(90,"s")]:
        rows=[x for x in results["experiments"] if x["role"] in ("primary","reporting_lag_sensitivity") and x["target_release_lag_days"]==release]
        for model in ["geography_ridge","aggregate_activity_ridge","simple_calls_to_teu"]:
            ax.plot([x["flow_lag_days"] for x in rows],[next(m["wape"] for m in x["metrics"] if m["model_id"]==model)*100 for x in rows],label=f"{NAMES[model]} · {release}d target",marker=marker,color=COLORS[model],ls="-" if release==60 else "--")
    ax.set_xticks([7,14,28]);ax.set_xlabel("Assumed shipping-data lag · calendar days");ax.set_ylabel("WAPE · %")
    ax.set_title("What changes when information arrives later?",loc="left",fontweight="bold",fontsize=18,pad=16)
    ax.grid(axis="y",alpha=.15);ax.legend(fontsize=8,frameon=False,ncol=2)
    fig.supxlabel("Secondary sensitivities · current-vintage pseudo-real-time, not archived release vintages",fontsize=9)
    fig.savefig(out/"availability_sensitivity.png",dpi=170);plt.close(fig)
    # Static social artwork uses the actual benchmark evidence, not invented ships/metrics.
    fig=plt.figure(figsize=(12,6.3),facecolor="#f5f7fb")
    fig.text(.055,.87,"JG  /  SUPPLY CHAIN SHADOW INDEX",color="#2558d5",fontsize=13,weight="bold")
    fig.text(.055,.71,"Ports Before Reports",color="#172742",fontsize=33,weight="bold")
    sub="A simple benchmark beat geographic detail." if winner=="simple_calls_to_teu" else "Does gateway detail improve an import nowcast?"
    fig.text(.055,.60,sub,color="#526176",fontsize=18)
    ax=fig.add_axes([.31,.15,.61,.34]);three=["aggregate_activity_ridge","geography_ridge",primary["selected_benchmark"]]
    three=list(dict.fromkeys(three));v=[float(frame.set_index("model_id").loc[m,"wape"])*100 for m in three]
    b=ax.barh([NAMES[m] for m in three],v,color=[COLORS[m] for m in three],height=.6);ax.invert_yaxis();ax.bar_label(b,labels=[f"{x:.2f}%" for x in v],padding=7)
    ax.set_xlim(0,max(v)*1.24);ax.set_xlabel("2024–2025 WAPE · percent · lower is better",fontsize=10)
    fig.text(.055,.035,"Historical evaluation under assumed reporting lags. No live predictive or investment-return claim.",color="#526176",fontsize=10)
    fig.savefig(out/"project_thumbnail.png",dpi=150);plt.close(fig)
    return [str(p.relative_to(root)).replace("\\","/") for p in out.glob("*") if p.is_file()]
