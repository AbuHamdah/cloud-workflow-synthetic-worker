"""Authenticated, allow-listed Montage/MAQ worker; no shell or arbitrary command API."""
import hashlib
import hmac
import json
import os
import platform
import re
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

TOKEN=os.environ.get('WORKER_TOKEN','')
STORE=Path('/store')
STORE.mkdir(exist_ok=True)
INSTANCE=uuid4().hex
LOCK=threading.Lock()
MAX_OBJECT=64*1024*1024
MAX_STORE=320*1024*1024

def path(name):
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}',name):
        raise ValueError('Invalid object name')
    return STORE/name

def metadata(file):
    return {'name':file.name,'bytes':file.stat().st_size,
            'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}

def execute(job):
    op=job['operation']; inputs=job.get('inputs',[]); output=path(job['output'])
    files=[path(name) for name in inputs]
    if not all(f.is_file() for f in files):raise ValueError('Missing input')
    commands=[]; outputs=[output]; stdout_file=None
    with tempfile.TemporaryDirectory(dir='/tmp') as temp:
        temp=Path(temp)
        if op=='mproject' and len(files)==2:
            commands=[['mProject',str(files[0]),str(output),str(files[1])]]
            outputs.append(path(output.stem+'_area.fits'))
        elif op=='madd' and len(files)>=3:
            images=temp/'images';images.mkdir()
            for file in files[:-1]: (images/file.name).symlink_to(file)
            commands=[['mImgtbl',str(images),str(temp/'images.tbl')],
                      ['mAdd','-p',str(images),str(temp/'images.tbl'),str(files[-1]),str(output)]]
            outputs.append(path(output.stem+'_area.fits'))
        elif op=='maq_fasta2bfa' and len(files)==1:
            commands=[['maq','fasta2bfa',str(files[0]),str(output)]]
        elif op=='maq_fastq2bfq' and len(files)==1:
            commands=[['maq','fastq2bfq',str(files[0]),str(output)]]
        elif op=='maq_map' and len(files)==2:
            commands=[['maq','map','-s','221126',str(output),str(files[0]),str(files[1])]]
        elif op=='maq_merge' and len(files)>=2:
            commands=[['maq','mapmerge',str(output),*[str(f) for f in files]]]
        elif op in ('maq_pileup','maq_mapview'):
            if op=='maq_pileup' and len(files)==2:
                commands=[['maq','pileup','-d',str(files[0]),str(files[1])]]
            elif op=='maq_mapview' and len(files)==1:
                commands=[['maq','mapview',str(files[0])]]
            else:raise ValueError('Input arity')
            stdout_file=output
        else:raise ValueError('Unsupported operation or input arity')
        receipts=[]
        for index,command in enumerate(commands):
            timing=temp/f'time{index}.txt'
            args=['/usr/bin/time','-f','%e|%U|%S|%M','-o',str(timing),*command]
            started=time.perf_counter()
            if stdout_file:
                with stdout_file.open('wb') as stream:
                    result=subprocess.run(args,stdout=stream,stderr=subprocess.PIPE,timeout=120)
                stdout=''
            else:
                result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
                stdout=result.stdout.decode(errors='replace')[-4000:]
            elapsed=time.perf_counter()-started
            values=timing.read_text().strip().splitlines()[-1].split('|')
            receipt={'argv':command,'returncode':result.returncode,'elapsed_s':elapsed,
                     'user_s':float(values[1]),'system_s':float(values[2]),'peak_rss_kib':int(values[3]),
                     'stdout':stdout,'stderr':result.stderr.decode(errors='replace')[-4000:]}
            receipts.append(receipt)
            if result.returncode or 'stat="ERROR"' in stdout:
                raise RuntimeError(json.dumps({'command_failed':receipt}))
        if not all(f.is_file() for f in outputs):raise RuntimeError('Missing output')
        if sum(f.stat().st_size for f in STORE.iterdir() if f.is_file())>MAX_STORE:
            raise RuntimeError('Store limit')
        return {'operation':op,'commands':receipts,'outputs':[metadata(f) for f in outputs]}

class Worker(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    timeout=150
    def log_message(self,*args):pass
    def reply(self,status=200,body=b''):
        self.send_response(status);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def authorized(self):
        if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+TOKEN):
            self.close_connection=True;self.reply(401,b'Authentication required');return False
        return True
    def do_GET(self):
        if not self.authorized():return
        try:
            if self.path=='/health':self.reply()
            elif self.path=='/identity':
                boot=Path('/proc/sys/kernel/random/boot_id')
                identity={'instance':INSTANCE,'system':platform.system(),'kernel':platform.release(),
                          'machine':platform.machine(),'python':platform.python_version(),
                          'boot_id_sha256':hashlib.sha256(boot.read_bytes()).hexdigest(),
                          'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          'github_run_id':os.environ.get('GITHUB_RUN_ID'),
                          'github_repository':os.environ.get('GITHUB_REPOSITORY'),
                          'cpu_max':Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
                          'memory_max':Path('/sys/fs/cgroup/memory.max').read_text().strip(),
                          'packages':subprocess.check_output(['dpkg-query','-W','montage','maq','time'],text=True)}
                self.reply(body=json.dumps(identity).encode())
            elif self.path.startswith('/file/'):
                file=path(self.path[6:]);self.reply(body=file.read_bytes())
            else:self.reply(404,b'Unknown endpoint')
        except (ValueError,OSError) as error:self.reply(400,str(error).encode())
    def do_POST(self):
        if not self.authorized():return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<=length<=MAX_OBJECT:raise ValueError('Request size')
            body=self.rfile.read(length)
            if len(body)!=length:raise ValueError('Incomplete body')
            with LOCK:
                if self.path=='/reset':
                    for file in STORE.iterdir():
                        if file.is_file():file.unlink()
                    self.reply()
                elif self.path.startswith('/file/'):
                    file=path(self.path[6:])
                    used=sum(f.stat().st_size for f in STORE.iterdir() if f.is_file() and f!=file)
                    if used+length>MAX_STORE:raise ValueError('Store limit')
                    file.write_bytes(body);self.reply(body=json.dumps(metadata(file)).encode())
                elif self.path=='/run':self.reply(body=json.dumps(execute(json.loads(body))).encode())
                else:self.reply(404,b'Unknown endpoint')
        except (ValueError,KeyError,TypeError,OSError,RuntimeError,subprocess.TimeoutExpired) as error:
            self.reply(400,json.dumps({'error':str(error)}).encode())

if __name__=='__main__':
    if len(TOKEN)<32:raise SystemExit('WORKER_TOKEN must have at least 32 characters')
    ThreadingHTTPServer(('0.0.0.0',8900),Worker).serve_forever()
