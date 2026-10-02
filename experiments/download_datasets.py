"""Resumable official downloads, archive validation and safe extraction."""
import concurrent.futures
import hashlib
import json
import shutil
import tarfile
import threading
import time
from pathlib import Path
import requests
from range_download import download as range_download

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'data'
LOCK = threading.Lock()
STATUS = {}


def update(key, **fields):
    with LOCK:
        STATUS.setdefault(key,{}).update(fields)
        path=DATA/'download_status.json'; temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(STATUS,indent=2)+'\n'); temporary.replace(path)


def fetch(item):
    key=item['dataset']+'/'+item['category']
    filename=item['url'].rsplit('/',1)[1]
    archive=DATA/'archives'/filename
    staging=archive.with_suffix(archive.suffix+'.part')
    destination=DATA/item['dataset']
    complete=destination/f".{item['category']}_extracted.json"
    if complete.exists():
        metadata=json.loads(complete.read_text())
        update(key,state='complete',**metadata,total_bytes=metadata['archive_bytes'],
               downloaded_bytes=metadata['archive_bytes']); return
    try:
        if shutil.disk_usage(DATA).free < 30*1024**3:
            raise OSError('Less than 30 GiB free; stopping downloads to preserve disk capacity')
        if not archive.exists():
            update(key,state='downloading',url=item['url'])
            print(f'RANGE DOWNLOAD {key}',flush=True)
            range_download(item['url'],staging,archive,lambda **fields:update(key,**fields))
        if not archive.exists():
            for attempt in range(4):
                offset=staging.stat().st_size if staging.exists() else 0
                headers={'Range':f'bytes={offset}-'} if offset else {}
                try:
                    with requests.get(item['url'],headers=headers,stream=True,timeout=(30,90)) as response:
                        response.raise_for_status()
                        if offset and response.status_code != 206:
                            offset=0
                        total=int(response.headers.get('Content-Length',0))+offset
                        if 'html' in response.headers.get('Content-Type',''):
                            raise ValueError('Download returned HTML, not an archive')
                        print(f'DOWNLOAD {key} {total/1024**3:.2f} GiB offset={offset}',flush=True)
                        update(key,state='downloading',url=item['url'],total_bytes=total,downloaded_bytes=offset)
                        last=time.monotonic()
                        with staging.open('ab' if offset else 'wb') as stream:
                            for chunk in response.iter_content(1024*1024):
                                stream.write(chunk); offset+=len(chunk)
                                if time.monotonic()-last>5:
                                    update(key,downloaded_bytes=offset); last=time.monotonic()
                        if total and offset!=total:
                            raise ValueError('Incomplete archive download')
                    staging.replace(archive); break
                except (requests.RequestException,ValueError):
                    if attempt==3: raise
                    time.sleep(2)
        digest=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()
        update(key,state='extracting',archive_sha256=digest,archive_bytes=archive.stat().st_size)
        destination.mkdir(parents=True,exist_ok=True)
        count=0
        with tarfile.open(archive,'r:*') as tar:
            for member in tar:
                target=(destination/member.name).resolve()
                if not target.is_relative_to(destination.resolve()) or member.issym() or member.islnk():
                    raise ValueError(f'Unsafe archive member: {member.name}')
                if not member.isdir() and not member.isfile():
                    continue
                tar.extract(member,destination,filter='data'); count+=1
        metadata={'url':item['url'],'archive_sha256':digest,'archive_bytes':archive.stat().st_size,'members':count}
        complete.write_text(json.dumps(metadata,indent=2)+'\n')
        update(key,state='complete',downloaded_bytes=archive.stat().st_size,**metadata)
        print(f'COMPLETE {key} members={count}',flush=True)
    except Exception as error:
        update(key,state='failed',error=str(error))
        print(f'FAILED {key}: {error}',flush=True)


if __name__=='__main__':
    DATA.mkdir(exist_ok=True); (DATA/'archives').mkdir(exist_ok=True)
    status_file=DATA/'download_status.json'
    if status_file.exists(): STATUS.update(json.loads(status_file.read_text()))
    items=json.loads((ROOT/'experiments/datasets.json').read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(fetch,items))
    if any(v.get('state')!='complete' for v in STATUS.values()): raise SystemExit(1)
