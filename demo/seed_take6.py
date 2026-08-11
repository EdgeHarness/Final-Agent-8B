"""Seed the take 6 fixture: Dana's email plus the attachment it points at.

Run from `standalone/`:  ../.venv/bin/python ../demo/seed_take6.py

Idempotent. The numbers live in q3_raw.xlsx, NOT in the email body, so the
agent has to open the file to get them. Reading is the story; a model that
retypes figures from prose is the failure mode this fixture removes.
"""
import json
import os

from openpyxl import Workbook

WS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "..", "standalone", "agents", "8b", "workspace")
FILES = os.path.join(WS, "files")
STATE = os.path.join(WS, "state.json")

ROWS = [
    ("Region", "Q2", "Q3"),
    ("West", 1105000, 1240000),
    ("East", 802000, 845000),
    ("Central", 415000, 392000),
    ("Online", 498000, 610000),
]

BODY = (
    "Morning! Final Q3 landed. I dropped the export in q3_raw.xlsx, it has Q2 "
    "and Q3 side by side.\n\n"
    "Could you pull the Q3 column into a clean spreadsheet with a total row, "
    "and turn the same numbers into a short deck for Wednesday's review?\n\n"
    "Thanks, Dana"
)


def main():
    os.makedirs(FILES, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Q3"
    for row in ROWS:
        ws.append(row)
    for cell in ("B2", "B3", "B4", "B5", "C2", "C3", "C4", "C5"):
        ws[cell].number_format = "#,##0"
    wb.save(os.path.join(FILES, "q3_raw.xlsx"))

    state = json.load(open(STATE))
    state["emails"] = [e for e in state["emails"] if e["id"] != "e11"]
    state["emails"].append({
        "id": "e11", "from": "dana@corp.com", "date": "2026-07-20 08:40",
        "subject": "Q3 regional numbers - sheet and deck for Wednesday?",
        "body": BODY,
    })
    json.dump(state, open(STATE, "w"), indent=2, ensure_ascii=False)
    print("seeded q3_raw.xlsx and email e11")


if __name__ == "__main__":
    main()
