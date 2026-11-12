"""Typed numeric grounding and conservative daily-extremum claim checks."""
import re
from datetime import date

NUMBER = r"(?<![A-Za-z\d-])[-+]?\d[\d,]*(?:\.\d+)?"

def numeric_tokens(text):
    # ISO date separators are not negative signs. ST IDs are checked separately.
    text = re.sub(r"ST-?\d+", "", text, flags=re.I)
    text = re.sub(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", r"\1 \2 \3", text)
    return re.findall(NUMBER, text)

def numeric_grounding(answer, evidence):
    actual = set()
    def collect(value, key=""):
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            actual.add(float(value))
            if any(word in key for word in ("share","ratio","percentile")):
                actual.add(float(value)*100)
        elif isinstance(value, str):
            actual.update(float(x.replace(",","")) for x in numeric_tokens(value))
        elif isinstance(value, dict):
            for name, child in value.items():
                collect(child, name)
        elif isinstance(value, list):
            if key == "observed_dates":
                actual.add(float(len(set(value))))
            for child in value:
                collect(child, key)
    for item in evidence:
        collect(item.get("result"))
    text = re.sub(r"(?m)^\s*\d+[.)]\s*", "", answer)
    tokens, unmatched = numeric_tokens(text), []
    for token in tokens:
        number = float(token.replace(",",""))
        decimals = len(token.split(".")[-1]) if "." in token else None
        tolerance = .5 * 10**(-decimals) if decimals is not None else 1e-8
        if not any(abs(number-value) <= tolerance+1e-8 for value in actual):
            unmatched.append(token)
    return {"checked_numeric_tokens":len(tokens), "matched_numeric_tokens":len(tokens)-len(unmatched),
            "unmatched_numeric_tokens":unmatched, "passed":not unmatched,
            "method":"ISO 날짜·대여소 ID를 수치와 분리하고 실제 관측일 배열의 고유 일수를 포함. 문장 의미 전체 보증 아님."}

def daily_extrema(evidence):
    rows = []
    for call in evidence:
        result = call["result"]
        daily = result.get("daily") if call["tool"] == "get_region_overview" else None
        if not daily:
            continue
        for kind, choose in (("maximum",max),("minimum",min)):
            value = choose(row["rental_count"] for row in daily)
            rows.append({"kind":kind,"region_id":result.get("region_id"),
                         "value":value,"dates":[row["date"] for row in daily if row["rental_count"]==value]})
    return rows

def extrema_grounding(answer, evidence):
    extrema, failures, checked = daily_extrema(evidence), [], 0
    clauses = re.split(r"(?<=[.!?])\s+|\n|(?<=고),\s*|(?<=며),\s*|;\s*",answer)
    for clause in clauses:
        kinds = []
        if re.search(r"최대|최댓|가장\s*많|제일\s*많|최고",clause):
            kinds.append("maximum")
        if re.search(r"최소|최솟|가장\s*적|제일\s*적|최저",clause):
            kinds.append("minimum")
        dates = re.findall(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)",clause)
        # Only daily claims; hourly maxima and station rankings have other domains.
        if not extrema or not kinds or not (dates or re.search(r"일별|일일|날짜|날은|날이|\d+월\s*\d+일",clause)):
            continue
        korean_dates = re.findall(r"(\d{1,2})월\s*(\d{1,2})일",clause)
        counts = [int(x.replace(",","")) for x in re.findall(r"([\d,]+)\s*건",clause)]
        for kind in kinds:
            checked += 1
            valid = False
            for row in extrema:
                if row["kind"] != kind:
                    continue
                stated_dates = list(dates)
                years = {date.fromisoformat(d).year for d in row["dates"]}
                if korean_dates and len(years)==1:
                    year = next(iter(years))
                    stated_dates.extend(f"{year:04d}-{int(m):02d}-{int(d):02d}" for m,d in korean_dates)
                if counts and all(value == row["value"] for value in counts) and all(d in row["dates"] for d in stated_dates):
                    valid = True
                    break
            if not valid:
                failures.append({"kind":kind,"claim":clause[:300],
                                 "expected":[row for row in extrema if row["kind"]==kind]})
    hourly_checked, hourly_failures = hourly_extrema_grounding(answer, evidence)
    checked += hourly_checked
    failures.extend(hourly_failures)
    return {"passed":not failures,"checked_claims":checked,"unsupported_claims":failures,
            "method":"일별 최대·최소 비교의 날짜/건수를 실제 극값과 대조. 해석할 수 없는 비교는 보류."}

def hourly_extrema_grounding(answer, evidence):
    """Check hour/count pairs for observed station net inflow/outflow claims."""
    checked, failures = 0, []
    for clause in re.split(r"(?<=[.!?])\s+|\n|(?<=고),\s*|(?<=며),\s*|;\s*",answer):
        if not re.search(r"최대|최댓|가장\s*큰|가장\s*많|제일\s*많",clause):
            continue
        hours = [int(x) for x in re.findall(r"(\d{1,2})\s*시",clause)]
        if not hours or not re.search(r"순유입|순유출",clause):
            continue
        counts = [int(x.replace(",","")) for x in re.findall(r"([-+]?\d[\d,]*)\s*건",clause)]
        checked += 1
        valid = False
        expected = []
        for call in evidence:
            if call["tool"] != "get_station_details":
                continue
            station = call["result"].get("station",{})
            series = station.get("hourly_net_outflow")
            if not series or any(v is None for v in series):
                continue
            # Require an unambiguous direction in each clause.
            if "순유입" in clause and "순유출" in clause:
                continue
            incoming = "순유입" in clause
            value = min(series) if incoming else max(series)
            allowed = {value,abs(value)} if incoming else {value}
            at = [hour for hour,n in enumerate(series) if n==value]
            expected.append({"station_id":station.get("station_id"),"value":value,"hours":at})
            if counts and all(n in allowed for n in counts) and all(hour in at for hour in hours):
                valid = True
        if not valid:
            failures.append({"kind":"hourly_net_extremum","claim":clause[:300],"expected":expected})
    return checked, failures
