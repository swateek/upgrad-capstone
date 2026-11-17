"""Independent review of the 20 hand-check gold entries (main session, 2026-11-17; not the gold
builder's code). Run from the app folder:
    cd backend && uv run python -I ../pack/eval/gold/review_hand_check.py ..
"""

import json
import sys
from decimal import ROUND_HALF_UP
from decimal import Decimal as D

import yaml

APP = sys.argv[1]
GAL = D("3.785411784")
cents = lambda x: x.quantize(D("0.01"), ROUND_HALF_UP)
PARTNERS = {
    "BH",
    "CL",
    "CO",
    "IL",
    "JO",
    "KR",
    "MA",
    "OM",
    "CR",
    "DO",
    "SV",
    "GT",
    "HN",
    "NI",
    "PA",
    "PE",
    "CA",
    "MX",
    "SG",
}
COL2 = {"KP", "BY", "RU", "CU"}
CBP_CBI = {
    "AG",
    "AW",
    "BS",
    "BB",
    "BZ",
    "BO",
    "VG",
    "CO",
    "CR",
    "DM",
    "DO",
    "EC",
    "SV",
    "GD",
    "GT",
    "GY",
    "HT",
    "HN",
    "JM",
    "MS",
    "NI",
    "PA",
    "PE",
    "KN",
    "LC",
    "VC",
    "TT",
}
DEF_ABV = {"wine": 12.5, "sparkling_wine": 12.0, "beer": 5.0, "spirits": 40.0, "liqueur": 25.0}
VOL = {"fifth": 750, "magnum": 1500}
STICKS = {"pack": 20, "carton": 200}


def excise_per_l(item, abv):
    abv = D(str(abv))
    if item in ("spirits", "liqueur") or abv > 24:
        return abv * 2 / 100 * D("13.50") / GAL
    if item == "beer":
        return D(18) / 31 / GAL
    if item == "sparkling_wine":
        return D("3.40") / GAL
    rate = D("1.07") if abv <= 16 else D("1.57") if abv <= 21 else D("3.15")
    return rate / GAL


def compute(facts):
    p, basket = facts["profile"], facts["basket"]
    age = p.get("age")
    frm = p.get("arrived_directly_from")
    hrs = p.get("trip_hours")
    long_trip = hrs == ">=48" or (isinstance(hrs, (int, float)) and hrs >= 48)
    ex = 800 if ((long_trip or frm == "MX") and not p.get("exemption_used_last_30_days")) else 200
    out = {"exemption_usd": str(ex)}
    alc = [
        (i, l) for i, l in enumerate(basket, 1) if l["item"] in DEF_ABV and l.get("origin") != "CU"
    ]
    tob = [
        (i, l)
        for i, l in enumerate(basket, 1)
        if l["item"] in ("cigarettes", "cigars") and l.get("origin") != "CU"
    ]
    ml = {
        i: D(l.get("container_ml") or VOL.get(l.get("unit"), 750)) * D(l["quantity"])
        for i, l in alc
    }
    total_ml = sum(ml.values(), D(0))
    if ex == 200:
        sticks_ok = all(
            (D(l["quantity"]) * STICKS.get(l.get("unit"), 1))
            <= (50 if l["item"] == "cigarettes" else 10)
            for _, l in tob
        )
        within = total_ml <= 150 and sticks_ok
        allow = total_ml if within else D(0)
        out["alcohol_allowance_ml"] = "150"
        tob_allow = {"cigarettes": 10**9 if within else 0, "cigars": 10**9 if within else 0}
    else:
        if age is not None and age < 21:
            allow = D(0)
        else:
            benef = sum((ml[i] for i, l in alc if l.get("origin") in CBP_CBI), D(0))
            allow = D(2000) if (frm in CBP_CBI and benef >= 1000) else D(1000)
        out["alcohol_allowance_ml"] = str(allow)
        tob_allow = {
            "cigarettes": 0 if (age is not None and age < 21) else 200,
            "cigars": 0 if (age is not None and age < 21) else 100,
        }

    # allocation: highest (3% value/L + excise/L) first
    def key(il):
        i, l = il
        abv = l.get("abv") or DEF_ABV[l["item"]]
        val = D(str(l["value_usd"])) if l.get("value_usd") is not None else D(0)
        return -(D("0.03") * val / (ml[i] / 1000) + excise_per_l(l["item"], abv))

    left = allow
    duty_t = exc_t = D(0)
    for i, l in sorted(alc, key=key):
        take = min(left, ml[i])
        left -= take
        dut = ml[i] - take
        out[f"exempt_ml_{i}"] = str(take.normalize() if take == take.to_integral() else take)
        out[f"dutiable_ml_{i}"] = str(dut.normalize() if dut == dut.to_integral() else dut)
        if dut > 0:
            abv = l.get("abv") or DEF_ABV[l["item"]]
            origin = l.get("origin")
            rate = D(0) if origin in PARTNERS else D("0.04") if origin in COL2 else D("0.03")
            if l.get("value_usd") is not None:
                dval = D(str(l["value_usd"])) * dut / ml[i]
                out[f"dutiable_value_usd_{i}"] = str(cents(dval))
                d = cents(rate * dval)
                out[f"duty_usd_{i}"] = str(d)
                duty_t += d
            out[f"duty_rate_{i}"] = str(rate)
            e = cents(dut / 1000 * excise_per_l(l["item"], abv))
            out[f"excise_usd_{i}"] = str(e)
            exc_t += e
    for i, l in tob:
        n = D(l["quantity"]) * STICKS.get(l.get("unit"), 1)
        a = min(n, tob_allow[l["item"]])
        out[f"exempt_sticks_{i}"] = str(int(a))
        out[f"excess_sticks_{i}"] = str(int(n - a))
    if any(k.startswith("dutiable_value") for k in out):
        out.update(
            duty_total_usd=str(duty_t),
            excise_total_usd=str(exc_t),
            total_owed_usd=str(duty_t + exc_t),
        )
    return out


def read_lines(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


with open(f"{APP}/pack/eval/src/frozen.yaml", encoding="utf-8") as fh:
    src = {s["id"]: s for s in yaml.safe_load(fh)}
gold = {g["id"]: g for g in read_lines(f"{APP}/pack/eval/gold/gold.jsonl")}
docs = {d["doc_id"] for d in read_lines(f"{APP}/data/chunks/documents.jsonl")}
ids = [
    "A01",
    "A04",
    "A07",
    "A10",
    "B01",
    "B03",
    "C01",
    "C05",
    "C08",
    "D01",
    "D02",
    "E04",
    "F01",
    "G02",
    "G04",
    "G07",
    "G08",
    "G10",
    "I02",
    "I06",
]
for sid in ids:
    t = [x for x in gold[sid]["turns"] if x["outcome"] == "answered"]
    bad_cites = [
        a
        for x in gold[sid]["turns"]
        for c in x.get("citations", [])
        for a in c["acceptable"]
        if a not in docs
    ]
    if not t:
        print(
            sid,
            "no answered turn (",
            gold[sid]["turns"][-1]["outcome"],
            ") cites missing:",
            bad_cites,
        )
        continue
    g = {f["name"]: f["value"] for f in t[-1].get("figures", [])}
    mine = compute(src[sid]["facts"])
    diffs = {k: (g.get(k), v) for k, v in mine.items() if k in g and D(g[k]) != D(v)}
    missing = [k for k in mine if k not in g]
    extra = [k for k in g if k not in mine]
    print(
        sid,
        "figures:",
        "ALL MATCH" if not diffs else f"DIFF {diffs}",
        "| only-mine:",
        missing or "-",
        "| only-gold:",
        extra or "-",
        "| bad cite ids:",
        bad_cites or "none",
    )
