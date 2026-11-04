#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import os
ROOT=Path(__file__).resolve().parent
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def do_GET(self):
        if self.path in ('/health','/healthz'):
            self.send_response(200); self.send_header('Content-Type','text/plain; charset=utf-8'); self.end_headers(); self.wfile.write(b'OK'); return
        if self.path.rstrip('/') == '/admin': self.path='/admin.html'
        return super().do_GET()
    def log_message(self,fmt,*args): pass
if __name__=='__main__':
    port=int(os.environ.get('PORT','8080'))
    ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
