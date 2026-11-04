#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from email.parser import BytesParser
from email.policy import default
import mimetypes, os
ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("AUDIO_DIR", "/data"))
ALLOWED = {"ambient.mp3": 8*1024*1024, "scream-laugh.mp3": 2*1024*1024}
class Handler(BaseHTTPRequestHandler):
 def send_bytes(self,b,ct="text/plain; charset=utf-8",status=200):
  self.send_response(status); self.send_header("Content-Type",ct); self.send_header("Content-Length",str(len(b))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(b)
 def do_GET(self):
  p=urlsplit(self.path).path
  if p in ("/health","/healthz"): return self.send_bytes(b"OK")
  if p in ("/assets/ambient.mp3","/assets/scream-laugh.mp3"):
   f=DATA/p.rsplit("/",1)[-1]
   if not f.is_file(): return self.send_bytes(b"Audio not uploaded",status=404)
   return self.send_bytes(f.read_bytes(),"audio/mpeg")
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
  if u.path!="/upload": return self.send_error(404,"Not found")
  if not os.environ.get("AUDIO_UPLOAD_KEY") or parse_qs(u.query).get("key",[""])[0]!=os.environ["AUDIO_UPLOAD_KEY"]: return self.send_bytes(b"Forbidden",status=403)
  ct=self.headers.get("Content-Type","")
  if "multipart/form-data" not in ct: return self.send_bytes(b"Expected multipart form",status=400)
  try: n=int(self.headers.get("Content-Length","0"))
  except ValueError: n=0
  if n<=0 or n>11*1024*1024: return self.send_bytes(b"Invalid upload size",status=413)
  msg=BytesParser(policy=default).parsebytes(b"Content-Type: "+ct.encode("ascii")+b"\r\nMIME-Version: 1.0\r\n\r\n"+self.rfile.read(n))
  saved=[]; DATA.mkdir(parents=True,exist_ok=True)
  for part in msg.iter_parts():
   name=part.get_param("name",header="content-disposition")
   if name not in ALLOWED or not part.get_filename(): continue
   payload=part.get_payload(decode=True) or b""
   if not payload or len(payload)>ALLOWED[name]: return self.send_bytes(("Invalid size: "+name).encode(),status=400)
   if not (payload.startswith(b"ID3") or (len(payload)>1 and payload[0]==255 and payload[1]&224==224)): return self.send_bytes(("Not a valid MP3: "+name).encode(),status=400)
   (DATA/name).write_bytes(payload); saved.append(name)
  if not saved: return self.send_bytes(b"No accepted audio files",status=400)
  return self.send_bytes(("Uploaded: "+", ".join(saved)).encode())
 def log_message(self,fmt,*args): print("%s - %s"%(self.address_string(),fmt%args),flush=True)
if __name__=="__main__":
 port=int(os.environ.get("PORT","8080")); print(f"JUST MAGIC listening on 0.0.0.0:{port}; root={ROOT}; audio={DATA}",flush=True); ThreadingHTTPServer(("0.0.0.0",port),Handler).serve_forever()
