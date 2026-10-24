#!/usr/bin/env python3
"""일일 종가 수집 스크립트 (파이썬 기본 기능만 사용, 별도 설치 없음).

config.json 의 자산 목록을 읽어 일봉 종가를 받아 data/data.json 으로 저장합니다.

데이터 출처 (자산마다 위에서부터 차례로 시도)
  1. Yahoo Finance 차트 API   - 무료, 키 없음. 주식·ETF·금·환율·암호화폐 전부 가능
  2. Binance 공개 시세 API    - 무료, 키 없음. 암호화폐 보조용 (config 의 "binance" 항목)
  3. Twelve Data              - 유료/무료 키 방식. 환경변수 TWELVEDATA_API_KEY 가 있을 때만 사용

종가가 아직 확정되지 않은 마지막 봉(장중, 또는 UTC 기준 오늘 암호화폐 봉)은 버립니다.
특정 자산 수집에 실패하면 이전 data.json 의 값을 그대로 유지하고 errors 에 이유를 남깁니다.
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
OUT_PATH = ROOT / "data" / "data.json"
USER_AGENT = "Mozilla/5.0 (compatible; sigma-scanner/1.0)"
MIN_BARS = 60          # 이보다 짧은 시계열은 실패로 간주
REQUEST_PAUSE = 0.4    # 요청 사이 대기(초). 차단 방지용


# ---------------------------------------------------------------- 공통 도구

def http_get_json(url, retries=3, timeout=30):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (400, 401, 403, 404):   # 재시도해도 소용없는 오류
                break
        except Exception as e:                   # 네트워크 일시 오류
            last_err = e
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{type(last_err).__name__}: {last_err}")


def finalize(pairs):
    """(날짜문자열, 종가) 목록 -> 날짜 중복 제거, 양수만, 날짜순 정렬."""
    by_date = {}
    for d, c in pairs:
        if c is not None and c == c and c > 0:
            by_date[d] = float(c)          # 같은 날짜가 두 번 오면 나중 값을 사용
    dates = sorted(by_date)
    return dates, [by_date[d] for d in dates]


# ---------------------------------------------------------------- Yahoo

class MissingBar(RuntimeError):
    """야후가 이미 끝난 날의 종가를 비워서(null) 보낸 경우"""


def parse_yahoo(payload, now_ts, strict=False):
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise RuntimeError(f"Yahoo 오류: {chart['error']}")
    result = (chart.get("result") or [None])[0]
    if not result or not result.get("timestamp"):
        raise RuntimeError("Yahoo 응답에 시계열이 없습니다")
    meta = result.get("meta") or {}
    ts = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    offset = int(meta.get("gmtoffset") or 0)

    # 아직 장이 진행 중이면 마지막 봉은 미확정 종가이므로 버린다
    reg = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    if ts and reg.get("start") and reg.get("end"):
        if ts[-1] >= reg["start"] and now_ts < reg["end"]:
            ts, closes = ts[:-1], closes[:-1]

    # 끝난 날인데 종가가 null 이면 야후의 일시적 누락이다
    if closes and closes[-1] is None:
        day = dt.datetime.fromtimestamp(ts[-1] + offset, dt.timezone.utc).date().isoformat()
        if strict:
            raise MissingBar(f"야후가 {day} 종가를 비워서 보냈습니다")
        print(f"  [경고] 야후가 {day} 종가를 비워서 보냈습니다. 그 날은 빼고 계산합니다")

    rows = []
    for t, c in zip(ts, closes):
        d = dt.datetime.fromtimestamp(t + offset, dt.timezone.utc).date().isoformat()
        rows.append((d, c))
    return finalize(rows)


def fetch_yahoo(asset, years):
    now = int(time.time())
    start = now - int(years * 365.25 * 86400)
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(asset['symbol'])}?period1={start}&period2={now}"
           "&interval=1d&includePrePost=false&events=div%2Csplit")
    for attempt in range(3):
        payload = http_get_json(url)
        if asset["symbol"] in DEBUG_SYMBOLS and attempt == 0:
            debug_yahoo(asset["symbol"], payload, now)
        try:
            return parse_yahoo(payload, now, strict=True)
        except MissingBar as e:
            if attempt < 2:
                time.sleep(10)          # 잠시 뒤 다시 받으면 채워지는 경우가 많다
                continue
            if asset.get("binance"):    # 암호화폐는 다음 출처(Binance)로 넘긴다
                raise
            print(f"  [경고] {asset['symbol']}: {e}")
            return parse_yahoo(payload, now, strict=False)


# 일부 자산은 야후가 돌려준 원본 값을 로그에 그대로 찍어 날짜 문제를 점검한다
DEBUG_SYMBOLS = {"SPY", "META", "BTC-USD", "005930.KS"}


def debug_yahoo(symbol, payload, now):
    try:
        iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%m-%d %H:%M:%SZ")
        res = payload["chart"]["result"][0]
        meta = res.get("meta") or {}
        ts = res.get("timestamp") or []
        closes = res["indicators"]["quote"][0]["close"]
        reg = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
        print(f"  [점검 {symbol}] 지금={iso(now)} 마지막시세시각={iso(meta['regularMarketTime']) if meta.get('regularMarketTime') else None}"
              f" 현재가={meta.get('regularMarketPrice')} 정규장={iso(reg['start']) if reg.get('start') else None}~{iso(reg['end']) if reg.get('end') else None}")
        for t, c in list(zip(ts, closes))[-3:]:
            print(f"  [점검 {symbol}] 봉 {iso(t)} 종가={c}")
    except Exception as e:  # noqa: BLE001
        print(f"  [점검 {symbol}] 실패: {e}")


# ---------------------------------------------------------------- Binance

def parse_binance(klines, now_ms):
    rows = []
    for k in klines:
        open_ms, close_price, close_ms = k[0], float(k[4]), k[6]
        if close_ms >= now_ms:            # 아직 마감 전인 봉
            continue
        d = dt.datetime.fromtimestamp(open_ms / 1000, dt.timezone.utc).date().isoformat()
        rows.append((d, close_price))
    return finalize(rows)


def fetch_binance(asset, years):
    if not asset.get("binance"):
        raise RuntimeError("config 에 binance 심볼이 없습니다")
    need = int(years * 366) + 5
    now_ms = int(time.time() * 1000)
    end_ms = None
    klines = []
    while len(klines) < need:
        url = ("https://data-api.binance.vision/api/v3/klines?"
               f"symbol={asset['binance']}&interval=1d&limit=1000")
        if end_ms:
            url += f"&endTime={end_ms}"
        batch = http_get_json(url)
        if not batch:
            break
        klines = batch + klines
        end_ms = batch[0][0] - 1
        if len(batch) < 1000:
            break
        time.sleep(REQUEST_PAUSE)
    return parse_binance(klines, now_ms)


# ---------------------------------------------------------------- Twelve Data

def parse_twelvedata(payload):
    if payload.get("status") == "error" or "values" not in payload:
        raise RuntimeError(f"Twelve Data 오류: {payload.get('message', payload)}")
    rows = [(v["datetime"][:10], float(v["close"])) for v in payload["values"]]
    return finalize(rows)


def fetch_twelvedata(asset, years):
    key = os.environ.get("TWELVEDATA_API_KEY", "").strip()
    if not key:
        raise RuntimeError("TWELVEDATA_API_KEY 가 설정되지 않았습니다")
    sym = asset.get("td") or (asset["symbol"] if re.fullmatch(r"[A-Z]+", asset["symbol"]) else None)
    if not sym:
        raise RuntimeError("Twelve Data 심볼을 알 수 없습니다 (config 에 td 항목을 추가하세요)")
    size = int(years * 366) + 5
    url = ("https://api.twelvedata.com/time_series?"
           f"symbol={urllib.parse.quote(sym)}&interval=1day&outputsize={size}&order=ASC&apikey={key}")
    time.sleep(8)                         # 무료 요금제 분당 호출 제한 회피
    return parse_twelvedata(http_get_json(url))


PROVIDERS = [("yahoo", fetch_yahoo), ("binance", fetch_binance), ("twelvedata", fetch_twelvedata)]


def fetch_asset(asset, years):
    problems = []
    for name, fn in PROVIDERS:
        try:
            dates, closes = fn(asset, years)
            if len(dates) < MIN_BARS:
                raise RuntimeError(f"데이터가 너무 짧습니다 ({len(dates)}개)")
            return name, dates, closes, problems
        except Exception as e:
            problems.append(f"{name}: {e}")
            time.sleep(REQUEST_PAUSE)
    raise RuntimeError(" | ".join(problems))


# ---------------------------------------------------------------- 실행

def sanity_warnings(symbol, dates, closes):
    out = []
    for i in range(1, len(closes)):
        move = closes[i] / closes[i - 1] - 1
        if abs(move) > 0.5:
            out.append(f"{symbol} {dates[i]} 전일 대비 {move * 100:+.0f}% (오류 값인지 확인 필요)")
    return out


def load_previous():
    try:
        return json.loads(OUT_PATH.read_text(encoding="utf-8")).get("assets", {})
    except Exception:
        return {}


def write_output(doc):
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ['{']
    lines.append(f'"version": 1, "demo": false, "generated_at": {json.dumps(doc["generated_at"])}, '
                 f'"history_years": {doc["history_years"]},')
    lines.append(f'"errors": {json.dumps(doc["errors"], ensure_ascii=False)},')
    lines.append(f'"pairs": {json.dumps(doc["pairs"], ensure_ascii=False)},')
    lines.append('"assets": {')
    items = list(doc["assets"].items())
    for i, (sym, a) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append(f'{json.dumps(sym)}: {json.dumps(a, ensure_ascii=False, separators=(",", ":"))}{comma}')
    lines.append('}')
    lines.append('}')
    tmp = OUT_PATH.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))   # 저장 결과가 올바른 JSON 인지 확인
    tmp.replace(OUT_PATH)


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    years = config.get("history_years", 3)
    previous = load_previous()
    assets_out, errors, warnings = {}, {}, []
    ok = 0

    print(f"{len(config['assets'])}개 자산 수집 시작 (최근 {years}년)")
    for i, asset in enumerate(config["assets"], 1):
        sym = asset["symbol"]
        try:
            source, dates, closes, problems = fetch_asset(asset, years)
            assets_out[sym] = {
                "name": asset["name"], "category": asset["category"], "source": source,
                "dates": dates, "close": [round(c, 6) for c in closes],
            }
            warnings += sanity_warnings(sym, dates, closes)
            ok += 1
            note = f" (앞선 출처 실패: {problems[0]})" if problems else ""
            print(f"[{i:>2}/{len(config['assets'])}] OK   {sym:<10} {source:<10} {len(dates)}개, 마지막 {dates[-1]}{note}")
        except Exception as e:
            errors[sym] = str(e)[:300]
            print(f"[{i:>2}/{len(config['assets'])}] FAIL {sym:<10} {e}")
            if sym in previous:               # 이전 값 유지
                kept = dict(previous[sym])
                kept["stale"] = True
                assets_out[sym] = kept
        time.sleep(REQUEST_PAUSE)

    if ok == 0:
        print("모든 자산 수집에 실패했습니다. 기존 data.json 은 그대로 둡니다.")
        return 1

    known = set(assets_out)
    pairs = []
    for p in config.get("pairs", []):
        if p["a"] in known and p["b"] in known:
            pairs.append(p)
        else:
            print(f"경고: 비율 쌍 {p['id']} 의 자산이 없어 건너뜁니다")

    doc = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "history_years": years, "errors": errors, "pairs": pairs, "assets": assets_out,
    }
    write_output(doc)
    print(f"\n완료: 성공 {ok}개, 실패 {len(errors)}개 -> {OUT_PATH}")
    for w in warnings[:20]:
        print("점검:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
