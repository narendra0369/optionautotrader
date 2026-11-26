"""V67 isolated AWS QA process-crash script: no persistent DB writes or broker calls.
Run only as stand-alone QA via Ubuntu. No production service restarts.
For ready-to-run package see OPTIONX_V67_EPHEMERAL_QA_RECOVERY.zip.
"""
import getpass,multiprocessing as mp,os,signal,sys,time
import psycopg
HOST="aws-1-ap-southeast-1.pooler.supabase.com"
LOCK=(670026,67)
def db(user,pwd):
    return psycopg.connect(host=HOST,port=5432,dbname="postgres",user=user,password=pwd,sslmode="require",connect_timeout=10,autocommit=True)
def child(user,pwd,pipe):
    with db(user,pwd) as c:
        c.execute("SELECT pg_advisory_lock(%s,%s)",LOCK)
        os.write(pipe,b"LOCKED")
        time.sleep(60)
def run():
    user=os.environ.get("OPTIONX_DB_QA_USER","").strip()
    if user!="postgres.yghijfzwsvmzaffllszl": raise RuntimeError("POOLER_USER_NOT_CONFIGURED")
    pwd=getpass.getpass("Supabase password (not echoed): ")
    r,w=os.pipe()
    proc=mp.Process(target=child,args=(user,pwd,w),daemon=True)
    try:
        with db(user,pwd) as conn: assert conn.execute("SELECT 1").fetchone()[0]==1
        proc.start();os.close(w)
        import select
        ready,_,_=select.select([r],[],[],20)
        if not ready or os.read(r,6)!=b"LOCKED":raise RuntimeError("QA_CHILD_NOT_READY")
        with db(user,pwd) as check:
            held=check.execute("SELECT pg_try_advisory_lock(%s,%s)",LOCK).fetchone()[0]
            if held:
                check.execute("SELECT pg_advisory_unlock(%s,%s)",LOCK)
                raise RuntimeError("QA_LOCK_NOT_EXCLUSIVE")
        print("PASS: QA_LOCK_EXCLUSIVE")
        os.kill(proc.pid,signal.SIGKILL);proc.join(8)
        recovered=False
        for _ in range(12):
            with db(user,pwd) as check:
                recovered=check.execute("SELECT pg_try_advisory_lock(%s,%s)",LOCK).fetchone()[0]
                if recovered:check.execute("SELECT pg_advisory_unlock(%s,%s)",LOCK)
            if recovered:break
            time.sleep(1)
        if not recovered: raise RuntimeError("QA_LOCK_NOT_RELEASED")
        print("PASS: QA_CRASH_LOCK_RELEASE_AND_RECONNECT")
        print("NOT_TESTED: REAL_DB_OUTAGE_OR_PRODUCTION_WORKER_RESTART")
        print("NO_DB_WRITES; NO_BROKER_ORDERS; LIVE_OFF")
    finally:
        os.close(r)
        if proc.is_alive():proc.terminate();proc.join(2)
if __name__=="__main__":run()
