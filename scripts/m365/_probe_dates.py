# -*- coding: utf-8 -*-
"""Einmal-Probe (rein lesend): aelteste + neueste Mail je Postfach.
Zeigt, wie weit die Historie in M365 zurueckreicht (Host-Europe-Frage)."""
import csv
from pathlib import Path
from mail_lib import config
from mail_lib.auth import TokenProvider
from mail_lib.graph import GraphClient

HERE = Path(__file__).resolve().parent
cfg = config.load()
gc = GraphClient(TokenProvider(cfg))

# Postfaecher aus exo_sizes.csv (ItemCount>0, keine DiscoveryMailbox)
boxes = []
with (HERE / "exo_sizes.csv").open(encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        upn = (r.get("UPN") or "").strip()
        try:
            n = int(float(r.get("ItemCount") or 0))
        except ValueError:
            n = 0
        if upn and "DiscoverySearchMailbox" not in upn and n > 0:
            boxes.append((upn, n))
boxes.sort(key=lambda x: -x[1])

def one(upn, order):
    # aelteste (asc) bzw. neueste (desc) Mail ueber ALLE Ordner des Postfachs
    params = {
        "$select": "receivedDateTime,subject",
        "$top": "1",
        "$orderby": f"receivedDateTime {order}",
    }
    try:
        data = gc.get_json(f"/v1.0/users/{upn}/messages", params)
        v = data.get("value") or []
        if v:
            return (v[0].get("receivedDateTime") or "")[:10]
    except Exception as e:
        return f"FEHLER({type(e).__name__})"
    return "(leer)"

print(f"{'Postfach':40} {'Mails':>7}  {'aelteste':10}  {'neueste':10}")
print("-" * 74)
for upn, n in boxes:
    print(f"{upn:40} {n:>7}  {one(upn,'asc'):10}  {one(upn,'desc'):10}")
gc.close()
