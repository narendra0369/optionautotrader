"""ChartX OHLC-only bridge, staged; reuses an already verified owner RAM session. No login or order access."""
import codecs, datetime as dt, hashlib, hmac, json, math, os, re, ssl, threading, time
import angel_gateway
import urllib.request
from zoneinfo import ZoneInfo
MASTER_URL="https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
CANDLES_URL="https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData"
MAX_MASTER_BYTES=75*1024*1024
IST=ZoneInfo("Asia/Kolkata")
INDEX={"NIFTY":("NSE",{"nifty50"}),"BANKNIFTY":("NSE",{"niftybank","banknifty"}),"SENSEX":("BSE",{"sensex","bsesensex","spbsesensex","spbseindexsensex"}),"FINNIFTY":("NSE",{"niftyfinancialservices","niftyfinancialservice","finnifty"})}
INTERVAL={"1m":("ONE_MINUTE",60,3),"3m":("THREE_MINUTE",180,7),"5m":("FIVE_MINUTE",300,14),"10m":("TEN_MINUTE",600,25),"15m":("FIFTEEN_MINUTE",900,30),"30m":("THIRTY_MINUTE",1800,60),"1h":("ONE_HOUR",3600,100),"1d":("ONE_DAY",86400,365)}
LOCK=threading.Lock()
MASTER=None
CACHE={}
LAST=0
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None
def request(req,timeout):
    return urllib.request.build_opener(NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context())).open(req,timeout=timeout)
def authenticate(symbol,tf,stamp,signature,now=None):
    key=os.getenv("CHARTX_DATA_ACCESS_KEY","")
    if os.getenv("CHARTX_BRIDGE_ENABLED")!="1" or len(key)<32:
        raise PermissionError("ChartX bridge disabled")
    if symbol not in (*INDEX,"NIFTY_FUT") or tf not in INTERVAL:
        raise ValueError("Unsupported symbol/timeframe")
    if not isinstance(stamp,str) or not re.fullmatch(r"[0-9]{10}",stamp):
        raise PermissionError("Invalid bridge timestamp")
    if abs(int(time.time() if now is None else now)-int(stamp))>45:
        raise PermissionError("Expired bridge request")
    expected=hmac.new(key.encode(),("chartx-ohlc-v1|"+symbol+"|"+tf+"|"+stamp).encode(),hashlib.sha256).hexdigest()
    if not isinstance(signature,str) or not re.fullmatch(r"[a-f0-9]{64}",signature) or not hmac.compare_digest(expected,signature):
        raise PermissionError("Invalid bridge signature")
    owner=os.getenv("OPTIONX_OWNER_USER_ID","").strip()
    if not angel_gateway._owner_bound(owner):
        raise PermissionError("Owner is not configured")
    session=angel_gateway._clean_session(owner,time.time())
    if not session or not session.get("jwt") or not session.get("apiKey"):
        raise PermissionError("Angel owner session is not active; verify on original OPTIONX page")
    return session
def _stream_json_array(handle):
    """Stream potentially large official JSON array without materializing 150k rows.

    Each element is bounded to 1MB and the total input to 75MB.
    Reject truncated, malformed or unexpected top-level input.
    """
    decoder = json.JSONDecoder()
    utf8 = codecs.getincrementaldecoder("utf-8")()
    buffer, index, started, total = "", 0, False, 0
    need_delimiter, after_comma = False, False
    while True:
        while True:
            while index < len(buffer) and buffer[index].isspace():
                index += 1
            if not started:
                if index >= len(buffer): break
                if buffer[index] != "[":
                    raise ValueError("INSTRUMENT_MASTER_FORMAT")
                started, index = True, index + 1
                continue
            while index < len(buffer) and buffer[index].isspace():
                index += 1
            if index >= len(buffer): break
            if need_delimiter:
                if buffer[index] == ",":
                    index += 1
                    need_delimiter, after_comma = False, True
                    continue
                if buffer[index] != "]":
                    raise ValueError("INSTRUMENT_MASTER_FORMAT")
            if buffer[index] == "]":
                if after_comma or buffer[index + 1:].strip():
                    raise ValueError("INSTRUMENT_MASTER_FORMAT")
                return
            if buffer[index] != "{":
                raise ValueError("INSTRUMENT_MASTER_FORMAT")
            try:
                item, end = decoder.raw_decode(buffer, index)
            except json.JSONDecodeError:
                break
            if not isinstance(item, dict):
                raise ValueError("INSTRUMENT_MASTER_FORMAT")
            yield item
            need_delimiter, after_comma = True, False
            index = end
            if index > 64 * 1024:
                buffer, index = buffer[index:], 0
        if len(buffer) - index > 1024 * 1024:
            raise ValueError("INSTRUMENT_MASTER_OVERSIZED_ROW")
        chunk = handle.read(64 * 1024)
        if not isinstance(chunk, (bytes, bytearray)):
            raise ValueError("INSTRUMENT_MASTER_FORMAT")
        total += len(chunk)
        if total > MAX_MASTER_BYTES:
            raise ValueError("INSTRUMENT_MASTER_OVERSIZED")
        if not chunk:
            raise ValueError("INSTRUMENT_MASTER_TRUNCATED")
        try:
            buffer += utf8.decode(chunk)
        except UnicodeDecodeError:
            raise ValueError("INSTRUMENT_MASTER_ENCODING") from None


def resolve(rows,today):
    matches={k:[] for k in INDEX};futures=[]
    for row in rows:
        token=str(row.get("token",""));ex=row.get("exch_seg");name=re.sub(r"[^a-z0-9]","",str(row.get("symbol","")).lower())
        if not re.fullmatch(r"[0-9]{2,14}",token):continue
        for k,(exchange,names) in INDEX.items():
            if ex==exchange and name in names and not row.get("expiry") and row.get("instrumenttype") in ("AMXIDX","INDEX"):
                matches[k].append((ex,token,str(row["symbol"])))
        if ex=="NFO" and row.get("name")=="NIFTY" and row.get("instrumenttype")=="FUTIDX":
            try:
                expiry=dt.datetime.strptime(row["expiry"].upper(),"%d%b%Y").date()
                if expiry>=today and re.fullmatch(r"NIFTY[A-Z0-9]+FUT",row["symbol"]):futures.append((expiry,(ex,token,row["symbol"])))
            except (ValueError,KeyError,TypeError):pass
    out={k:next(iter(set(v))) for k,v in matches.items() if len(set(v))==1}
    if futures:
        nearest=min(x[0] for x in futures);v=set(x[1] for x in futures if x[0]==nearest)
        if len(v)==1:out["NIFTY_FUT"]=next(iter(v))
    return out
def instruments(now):
    global MASTER
    today=dt.datetime.fromtimestamp(now,IST).date()
    if MASTER and MASTER[0]==today and now-MASTER[1]<14400:return MASTER[2]
    with request(urllib.request.Request(MASTER_URL,headers={"Accept":"application/json","User-Agent":"ChartXReadOnly/1.0"}),30) as r:
        rows=resolve(_stream_json_array(r),today)
    if not rows:raise ValueError("Angel instrument master unavailable")
    MASTER=(today,now,rows);return rows
def clean_rows(rows,symbol,start,now,step):
    if not isinstance(rows,list) or len(rows)>20000:raise ValueError("Invalid broker candle response")
    out={}
    for row in rows:
        try:
            if not isinstance(row,list) or len(row)<5:continue
            d=dt.datetime.fromisoformat(row[0]);d=d if d.tzinfo else d.replace(tzinfo=IST);t=int(d.timestamp())
            o,h,l,c=map(float,row[1:5]);v=float(row[5]) if len(row)>5 and row[5] is not None and symbol=="NIFTY_FUT" else None
            if not all(map(math.isfinite,(o,h,l,c))) or min(o,h,l,c)<=0 or h<max(o,c) or l>min(o,c) or t<start or t>now or (v is not None and (not math.isfinite(v) or v<0)):continue
            if t in out:raise ValueError("Duplicate broker timestamp")
            # Intraday candles include potentially unfinished current candle; never use it as closed.
            partial=t+step>now
            out[t]={"time":t,"open":o,"high":h,"low":l,"close":c,"volume":v,"partial":partial}
        except (TypeError,ValueError,OverflowError):continue
    return sorted(out.values(),key=lambda r:r["time"])[-2000:]
def candles(symbol,tf,stamp,signature):
    global LAST
    session=authenticate(symbol,tf,stamp,signature)
    if not LOCK.acquire(blocking=False):raise ValueError("Angel request busy; retry")
    try:
        now=time.time();key=(symbol,tf,session["verifiedAt"]);cached=CACHE.get(key)
        if cached and now-cached[0]<45:return cached[1]
        if now-LAST<2:raise ValueError("Angel request rate limited; retry")
        LAST=now
        item=instruments(now).get(symbol)
        if not item:raise ValueError("Index/contract not uniquely verified in official master")
        exchange,token,contract=item;interval,step,days=INTERVAL[tf]
        end=dt.datetime.fromtimestamp(now,IST);start=end-dt.timedelta(days=days)
        headers={"Accept":"application/json","Content-Type":"application/json","User-Agent":"ChartXReadOnly/1.0","Authorization":"Bearer "+session["jwt"],"X-PrivateKey":session["apiKey"],"X-UserType":"USER","X-SourceID":"WEB",**angel_gateway.angel_client_identity_headers()}
        payload={"exchange":exchange,"symboltoken":token,"interval":interval,"fromdate":start.strftime("%Y-%m-%d %H:%M"),"todate":end.strftime("%Y-%m-%d %H:%M")}
        try:
            with request(urllib.request.Request(CANDLES_URL,headers=headers,data=json.dumps(payload).encode(),method="POST"),15) as r:
                raw=r.read(2000001)
            if len(raw)>2000000:raise ValueError()
            response=json.loads(raw)
        except Exception:raise ValueError("Angel candle request failed; verify session and broker access") from None
        if not isinstance(response,dict) or response.get("status") is not True:raise ValueError("Angel rejected candle request; verify session and access")
        rows=clean_rows(response.get("data"),symbol,int(start.timestamp())-step,int(now),step)
        if not rows:raise ValueError("Angel returned no valid candles")
        result={"candles":rows,"source":"Angel SmartAPI OHLC snapshot • "+contract,"contract":contract,"fetched_at":int(now),"interval_seconds":step,"status":"Historical REST snapshots; not tick stream"}
        if len(CACHE)>80:CACHE.clear()
        CACHE[key]=(now,result);return result
    finally:LOCK.release()
