"""Runs the eval set against the running app logic (in-process) and prints a pass/fail table.

Usage:  LLM_PROVIDER=mock python -m evals.run            # offline, deterministic
        LLM_PROVIDER=azure python -m evals.run            # real model (needs AZURE_OPENAI_* env)
Exit code 1 when the pass rate is below --min-pass (default 95).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings

settings.rate_limit_per_minute = 10**6  # evals hammer one client

from app.main import app, catalogue  # noqa: E402

ARABIC = re.compile(r"[؀-ۿ]")


def perfume(pid: str) -> dict:
    return catalogue.get(pid) or {}


def run_case(client: TestClient, case: dict) -> tuple[bool, list[str]]:
    sid = client.post("/api/session", json={"lang": "ar" if case.get("quiz") is None and case["messages"] and ARABIC.search(case["messages"][0]) else "en"}).json()["session_id"]
    reply, prev_max_price, consent_asked = None, None, False
    if case.get("quiz"):
        reply = client.post("/api/quiz", json={"session_id": sid, "answers": case["quiz"]}).json()
    else:
        for i, m in enumerate(case["messages"]):
            reply = client.post("/api/chat", json={"session_id": sid, "message": m}).json()
            if reply.get("intent") == "wishlist" and not reply.get("picks") and i < len(case["messages"]) - 1:
                consent_asked = True
            if reply.get("picks") and case.get("refine"):
                prev_max_price = max((p["price_aed"] or 0) for p in reply["picks"])
    if case.get("refine"):
        reply = client.post("/api/refine", json={"session_id": sid, "chip": case["refine"]}).json()
    checks, fails = case["checks"], []
    picks = reply.get("picks", [])
    pids = [p["perfume_id"] for p in picks]
    if "picks" in checks and len(picks) != checks["picks"]:
        fails.append(f"expected {checks['picks']} picks, got {len(picks)}")
    if "intent" in checks and reply.get("intent") != checks["intent"]:
        fails.append(f"intent {reply.get('intent')} != {checks['intent']}")
    if "lang" in checks:
        is_ar = bool(ARABIC.search(reply.get("reply", "")))
        if (checks["lang"] == "ar") != is_ar:
            fails.append(f"reply language wrong: {reply.get('reply','')[:60]}")
    for fam in checks.get("families_not", []):
        bad = [p["name"] for p in picks if p["family"] == fam]
        if bad:
            fails.append(f"family {fam} present: {bad}")
    if "families_in" in checks:
        bad = [p["name"] for p in picks if p["family"] not in checks["families_in"]]
        if bad:
            fails.append(f"family outside {checks['families_in']}: {bad}")
    for note in checks.get("notes_not", []):
        bad = [p["name"] for p in picks if note in {n["note"] for n in perfume(p["perfume_id"]).get("notes", [])}]
        if bad:
            fails.append(f"note {note} present: {bad}")
    if "notes_any" in checks:
        ok = [p["name"] for p in picks if {n["note"] for n in perfume(p["perfume_id"]).get("notes", [])} & set(checks["notes_any"])]
        if not ok:
            fails.append(f"no pick has any of {checks['notes_any']}")
    if "max_price" in checks:
        bad = [(p["name"], p["price_aed"]) for p in picks if p["price_aed"] is not None and p["price_aed"] > checks["max_price"]]
        if bad:
            fails.append(f"over budget: {bad}")
    if "max_strength" in checks:
        bad = [(p["name"], p["strength"]) for p in picks if p["strength"] > checks["max_strength"]]
        if bad:
            fails.append(f"too strong: {bad}")
    if "anchor" in checks:
        anchor = catalogue.find_by_name(checks["anchor"])
        if not anchor:
            fails.append("anchor missing from catalogue")
        else:
            a_acc = set(anchor["accords"])
            if checks.get("shared_accords_min"):
                bad = [p["name"] for p in picks if len(set(perfume(p["perfume_id"]).get("accords", {})) & a_acc) < checks["shared_accords_min"]]
                if bad:
                    fails.append(f"too few shared accords with {anchor['name']}: {bad}")
            if checks.get("price_below_anchor"):
                bad = [(p["name"], p["price_aed"]) for p in picks if p["price_aed"] and p["price_aed"] >= anchor["price_aed"]]
                if bad:
                    fails.append(f"not cheaper than anchor ({anchor['price_aed']}): {bad}")
            if anchor["perfume_id"] in pids:
                fails.append("anchor recommended to itself")
    if checks.get("layering") and not reply.get("layering"):
        fails.append("no layering pair")
    if checks.get("cheaper_than_previous_max") and prev_max_price is not None:
        bad = [(p["name"], p["price_aed"]) for p in picks if p["price_aed"] and p["price_aed"] >= prev_max_price]
        if bad:
            fails.append(f"not cheaper than previous max {prev_max_price}: {bad}")
    text = reply.get("reply", "")
    for frag in checks.get("reply_not_contains", []):
        if frag.lower() in text.lower():
            fails.append(f"reply contains '{frag}'")
    if "reply_contains_any" in checks and not any(f.lower() in text.lower() for f in checks["reply_contains_any"]):
        fails.append(f"reply lacks any of {checks['reply_contains_any']}: {text[:80]}")
    if "wishlist_min" in checks:
        wl = client.get(f"/api/wishlist?session_id={sid}").json()["wishlist"]
        if len(wl) < checks["wishlist_min"]:
            fails.append(f"wishlist has {len(wl)} items")
    if checks.get("consent_asked") and not consent_asked:
        fails.append("consent was not asked before saving")
    return (not fails), fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-pass", type=float, default=95.0)
    ap.add_argument("--only")
    args = ap.parse_args()
    cases = json.loads((Path(__file__).with_name("cases.json")).read_text(encoding="utf-8"))
    if args.only:
        cases = [c for c in cases if args.only in c["id"]]
    client = TestClient(app)
    passed = 0
    rows = []
    for case in cases:
        ok, fails = run_case(client, case)
        passed += ok
        rows.append((case["id"], case["type"], "PASS" if ok else "FAIL", "; ".join(fails)))
    width = max(len(r[0]) for r in rows)
    for r in rows:
        print(f"{r[2]}  {r[0]:<{width}}  {r[1]:<20} {r[3]}")
    rate = 100.0 * passed / max(1, len(cases))
    print(f"\n{passed}/{len(cases)} passed ({rate:.1f}%)  provider={settings.llm_provider if settings.llm_enabled else 'rules-only'}")
    out = Path(__file__).with_name("results")
    out.mkdir(exist_ok=True)
    (out / "latest.json").write_text(json.dumps([{"id": r[0], "type": r[1], "result": r[2], "detail": r[3]} for r in rows], indent=2, ensure_ascii=False))
    return 0 if rate >= args.min_pass else 1


if __name__ == "__main__":
    sys.exit(main())
