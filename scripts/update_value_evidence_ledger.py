"""Merge current report quotes into the persistent value evidence ledger."""
import argparse, json
from pathlib import Path
from app.value_evidence_ledger import merge_evidence_ledger

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report",required=True); p.add_argument("--ledger",required=True)
    p.add_argument("--results",default=None); p.add_argument("--output",required=True)
    a=p.parse_args()
    report=json.loads(Path(a.report).read_text())
    ledger_path=Path(a.ledger)
    previous=json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    results=json.loads(Path(a.results).read_text()) if a.results and Path(a.results).exists() else {}
    ledger=merge_evidence_ledger(previous,report,results)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(ledger,indent=2,ensure_ascii=False)+"\\n")
    print(json.dumps(ledger["summary"],sort_keys=True))
if __name__=="__main__": main()
