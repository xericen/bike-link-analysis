"""Export actual matched-station scatter plots for slides; no analytical writes."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from backend.research.presentation import read

OUT=Path("docs/method-validation-20261123")
COLORS={"high_high":"#2869bf","high_low":"#d87919","low_high":"#168779","low_low":"#8a97a8"}
LABELS={"high_high":"Both high","high_low":"High transit / low bike",
        "low_high":"Low transit / high bike","low_low":"Both low"}

def main():
    report=read("all")
    cities=[c for c in report["cities"] if c["demand_matrix"]["available"]]
    fig,axes=plt.subplots(1,len(cities),figsize=(12,5),squeeze=False)
    for ax,city in zip(axes[0],cities):
        data=city["demand_matrix"]
        for key,color in COLORS.items():
            rows=[r for r in data["rows"] if r["quadrant"]==key]
            ax.scatter(np.log1p([r["transit_total"] for r in rows]),
                       np.log1p([r["bike_activity_500m"] for r in rows]),
                       color=color,s=20,alpha=.75,label=f"{LABELS[key]} (n={len(rows)})")
        ax.axvline(np.log1p(data["transit_median"]),color="#8595a8",linestyle="--",linewidth=1)
        ax.axhline(np.log1p(data["bike_median"]),color="#8595a8",linestyle="--",linewidth=1)
        ax.set(title=f"{city['city'].title()} | matched stations: {data['matched_count']}",
               xlabel="log(1 + monthly transit boardings + alightings)",
               ylabel="log(1 + bicycle rentals + returns within 500m)")
        ax.legend(fontsize=8,loc="best")
        ax.grid(alpha=.15)
    fig.suptitle("December 2025 | Co-location of observed activity, not observed transfers",fontsize=12)
    fig.tight_layout()
    OUT.mkdir(exist_ok=True)
    for ext in ("png","svg"):
        fig.savefig(OUT/f"demand-matrix.{ext}",dpi=180,bbox_inches="tight")
    plt.close(fig)
    print("Saved PNG and SVG; Sejong excluded because comparable BRT demand is unavailable.")
if __name__=="__main__":main()
