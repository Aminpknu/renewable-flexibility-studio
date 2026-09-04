"""Append the latest market-wide Elexon BOALF snapshot to a deduplicated archive."""
from pathlib import Path
import json
from adapters.bm_acceptances import append_acceptance_archive, fetch_latest_bm_acceptances
from engine.bm_evidence import summarise_bm_acceptance_archive

ROOT=Path(__file__).resolve().parents[1]
archive=ROOT/'data'/'bm_acceptance_archive.csv'
summary_path=ROOT/'data'/'bm_acceptance_summary.json'
latest=fetch_latest_bm_acceptances()
combined=append_acceptance_archive(latest,archive)
summary=summarise_bm_acceptance_archive(combined)
summary.update({"source":"Elexon Insights BOALF latest market-wide endpoint","refresh_rows":len(latest)})
summary_path.write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
