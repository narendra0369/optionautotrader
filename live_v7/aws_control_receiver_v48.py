"""V48 local-only AWS signed owner-command receiver.

This binds 127.0.0.1 ONLY, to be accessed behind a separately configured
authenticated TLS reverse proxy, not opened publicly as raw HTTP.
No real order actions. Requires server-provisioned secret and dedicated
private SQLite storage. Do not run as root.
"""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from datetime import datetime,timezone
from pathlib import Path
from uuid import UUID
from .owner_control_store_v47 import open_control_store
from .signed_owner_commands_v48 import apply_signed_command,CommandRejected

class PrivateControlServer(ThreadingHTTPServer):
    allow_reuse_address=False
    daemon_threads=True
    def __init__(self,bind,handler,*,db_path,owner_id,key):
        if bind[0] not in ("127.0.0.1","::1"):
            raise ValueError("LOOPBACK_BIND_ONLY")
        if type(key) is not bytes or len(key)<32:
            raise ValueError("STRONG_SERVER_KEY_REQUIRED")
        self.db_path=str(db_path)
        self.owner_id=str(UUID(owner_id))
        self.key=key
        super().__init__(bind,handler)

class PrivateControlHandler(BaseHTTPRequestHandler):
    def log_message(self,format,*args):
        # Do not log URLs, headers, account IDs, signatures or raw payloads.
        pass
    def _reply(self,code,data):
        body=json.dumps(data,separators=(",",":")).encode("utf8")
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_POST(self):
        if self.path!="/v48/owner/control":
            return self._reply(404,{"error":"NOT_FOUND"})
        if self.headers.get("Content-Type","").split(";")[0].strip().lower()!="application/json":
            return self._reply(415,{"error":"JSON_REQUIRED"})
        try: size=int(self.headers.get("Content-Length","0"))
        except (TypeError,ValueError):size=0
        if size<10 or size>1024:
            return self._reply(413,{"error":"BODY_SIZE_INVALID"})
        signature=self.headers.get("X-OptionX-Signature","")
        try:
            body=json.loads(self.rfile.read(size))
            # Always open a separate connection; BEGIN IMMEDIATE fences
            # concurrent requests. Never persist raw bearer tokens.
            db=open_control_store(self.server.db_path)
            try:
                result=apply_signed_command(
                    db,data=body,signature=signature,
                    key=self.server.key,expected_owner=self.server.owner_id,
                    now=datetime.now(timezone.utc))
            finally:
                db.close()
            return self._reply(200,result)
        except (CommandRejected,ValueError,TypeError):
            return self._reply(403,{"error":"OWNER_COMMAND_REJECTED",
                                    "liveOrdersEnabled":False})
        except Exception:
            return self._reply(503,{"error":"CONTROL_STORE_UNAVAILABLE",
                                    "liveOrdersEnabled":False})
    def do_GET(self):
        return self._reply(404,{"error":"NOT_FOUND"})
    def do_OPTIONS(self):
        return self._reply(405,{"error":"METHOD_NOT_ALLOWED"})

def serve_local(*,db_path,owner_id,key,port=8766):
    if os.geteuid()==0:
        raise ValueError("NON_ROOT_PROCESS_REQUIRED")
    # Caller must prepare 0700 private directory as restricted OS user,
    # load secret key from root-provisioned secret manager / service config.
    db=open_control_store(db_path);db.close()
    app=PrivateControlServer(("127.0.0.1",port),PrivateControlHandler,
                             db_path=db_path,owner_id=owner_id,key=key)
    app.serve_forever()
