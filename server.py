#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from email.parser import BytesParser
from email.policy import default
import mimetypes, os, json, time, uuid, re

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("AUDIO_DIR", "/data"))
PHOTOS = DATA / "players"
ALLOWED_AUDIO = {"ambient.mp3": 8*1024*1024, "scream-laugh.mp3": 2*1024*1024}

class Handler(BaseHTTPRequestHandler):
 def send_bytes(self, b, ct="text/plain; charset=utf-8", status=200):
  self.send_response(status); self.send_header("Content-Type",ct); self.send_header("Content-Length",str(len(b))); self.send_header("Cache-Control","no-store"); self.send_header("X-Content-Type-Options","nosniff"); self.end_headers(); self.wfile.write(b)
 def json(self, obj, status=200): return self.send_bytes(json.dumps(obj,ensure_ascii=False).encode(), "application/json; charset=utf-8", status)
 def admin_ok(self, q):
  key = os.environ.get("AUDIO_UPLOAD_KEY","")
  return bool(key) and parse_qs(q).get("key",[""])[0] == key
 def do_GET(self):
  u=urlsplit(self.path); p=u.path
  if p in ("/health","/healthz"): return self.send_bytes(b"OK")
  if p in ("/assets/ambient.mp3","/assets/scream-laugh.mp3"):
   f=DATA/p.rsplit("/",1)[-1]
   if not f.is_file(): return self.send_bytes(b"Audio not uploaded",status=404)
   return self.send_bytes(f.read_bytes(),"audio/mpeg")
  if p == "/api/admin/sessions":
   if not self.admin_ok(u.query): return self.json({"error":"unauthorized"},401)
   rows=[]
   if PHOTOS.exists():
    for folder in sorted((x for x in PHOTOS.iterdir() if x.is_dir()),key=lambda x:x.stat().st_mtime,reverse=True):
     files=sorted(folder.glob("*.jpg"))
     rows.append({"id":folder.name,"created":time.strftime("%Y-%m-%d %H:%M:%S",time.gmtime(folder.stat().st_mtime)),"photos":[f.name for f in files]})
   return self.json({"sessions":rows})
  if p.startswith("/api/admin/photo/"):
   if not self.admin_ok(u.query): return self.send_bytes(b"Unauthorized",status=401)
   parts=p.split("/")
   if len(parts)!=6: return self.send_bytes(b"Not found",status=404)
   sid,name=parts[4],parts[5]
   if not re.fullmatch(r"[a-f0-9]{12}",sid) or not re.fullmatch(r"[1-5]\.jpg",name): return self.send_bytes(b"Not found",status=404)
   f=PHOTOS/sid/name
   if not f.is_file(): return self.send_bytes(b"Not found",status=404)
   return self.send_bytes(f.read_bytes(),"image/jpeg")
  routes={"/":"index.html","/index.html":"index.html","/admin":"admin.html","/admin/":"admin.html","/admin.html":"admin.html","/upload":"upload.html","/upload/":"upload.html"}
  fn=routes.get(p)
  if fn is None and p.startswith("/assets/"): fn=p.lstrip("/")
  if fn is None: return self.send_error(404,"Not found")
  f=(ROOT/fn).resolve()
  if ROOT not in f.parents or not f.is_file(): return self.send_error(404,"Not found")
  ct=mimetypes.guess_type(str(f))[0] or "application/octet-stream"
  if ct.startswith("text/") or ct in ("application/javascript","application/json"): ct+="; charset=utf-8"
  return self.send_bytes(f.read_bytes(),ct)
 def do_POST(self):
  u=urlsplit(self.path)
  if u.path == "/api/photos":
   ct=self.headers.get("Content-Type","")
   if "multipart/form-data" not in ct: return self.json({"error":"multipart required"},400)
   try: n=int(self.headers.get("Content-Length","0"))
   except ValueError: n=0
   if n<=0 or n>16*1024*1024: return self.json({"error":"invalid upload size"},413)
   msg=BytesParser(policy=default).parsebytes(b"Content-Type: "+ct.encode("ascii")+b"\r\nMIME-Version: 1.0\r\n\r\n"+self.rfile.read(n))
   incoming={}
   for part in msg.iter_parts():
    field=part.get_param("name",header="content-disposition")
    if field and re.fullmatch(r"photo[1-5]",field):
     payload=part.get_payload(decode=True) or b""
     if not payload or len(payload)>3*1024*1024 or not payload.startswith(b"\xff\xd8\xff"): return self.json({"error":"invalid jpeg"},400)
     incoming[field]=payload
   if len(incoming)!=5: return self.json({"error":"exactly five photos required"},400)
   PHOTOS.mkdir(parents=True,exist_ok=True)
   sid=uuid.uuid4().hex[:12]; folder=PHOTOS/sid; folder.mkdir()
   for i in range(1,6): (folder/f"{i}.jpg").write_bytes(incoming[f"photo{i}"])
   (folder/"consent.json").write_text(json.dumps({"consent":True,"created":int(time.time())}))
   return self.json({"ok":True,"id":sid})
  if u.path!="/upload": return self.send_error(404,"Not found")
  if not self.admin_ok(u.query): return self.send_bytes(b"Forbidden",status=403)
  ct=self.headers.get("Content-Type","")
  if "multipart/form-data" not in ct: return self.send_bytes(b"Expected multipart form",status=400)
  try: n=int(self.headers.get("Content-Length","0"))
  except ValueError: n=0
  if n<=0 or n>11*1024*1024: return self.send_bytes(b"Invalid upload size",status=413)
  msg=BytesParser(policy=default).parsebytes(b"Content-Type: "+ct.encode("ascii")+b"\r\nMIME-Version: 1.0\r\n\r\n"+self.rfile.read(n))
  saved=[]; DATA.mkdir(parents=True,exist_ok=True)
  for part in msg.iter_parts():
   name=part.get_param("name",header="content-disposition")
   if name not in ALLOWED_AUDIO or not part.get_filename(): continue
   payload=part.get_payload(decode=True) or b""
   if not payload or len(payload)>ALLOWED_AUDIO[name]: return self.send_bytes(("Invalid size: "+name).encode(),status=400)
   if not (payload.startswith(b"ID3") or (len(payload)>1 and payload[0]==255 and payload[1]&224==224)): return self.send_bytes(("Not a valid MP3: "+name).encode(),status=400)
   (DATA/name).write_bytes(payload); saved.append(name)
  if not saved: return self.send_bytes(b"No accepted audio files",status=400)
  return self.send_bytes(("Uploaded: "+", ".join(saved)).encode())
 def do_DELETE(self):
  u=urlsplit(self.path)
  if u.path!="/api/admin/session": return self.send_error(404,"Not found")
  if not self.admin_ok(u.query): return self.json({"error":"unauthorized"},401)
  sid=parse_qs(u.query).get("id",[""])[0]
  if not re.fullmatch(r"[a-f0-9]{12}",sid): return self.json({"error":"invalid id"},400)
  folder=PHOTOS/sid
  if not folder.is_dir(): return self.json({"error":"not found"},404)
  for f in folder.iterdir():
   if f.is_file(): f.unlink()
  folder.rmdir()
  return self.json({"ok":True})
 def log_message(self,fmt,*args): print("%s - %s"%(self.address_string(),fmt%args),flush=True)

if __name__=="__main__":
 port=int(os.environ.get("PORT","8080")); print(f"JUST MAGIC listening on 0.0.0.0:{port}; root={ROOT}; data={DATA}",flush=True); ThreadingHTTPServer(("0.0.0.0",port),Handler).serve_forever()
