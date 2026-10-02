"""Bounded four-connection range downloads, preserving existing partial bytes."""
import concurrent.futures
import math
import shutil
import time
from pathlib import Path
import requests


def download(url: str, staging: Path, archive: Path, progress):
    response=requests.head(url,timeout=30); response.raise_for_status()
    total=int(response.headers['Content-Length'])
    chunk_size=64*1024**2
    chunks=[staging.with_name(staging.name+f'.chunk{index:04d}') for index in range(math.ceil(total/chunk_size))]
    if staging.exists():
        # Migrate prior sequential download without discarding completed bytes.
        with staging.open('rb') as stream:
            for path in chunks:
                data=stream.read(chunk_size)
                if not data: break
                if not path.exists() or path.stat().st_size<len(data): path.write_bytes(data)
        staging.unlink()
    progress(total_bytes=total,downloaded_bytes=sum(p.stat().st_size for p in chunks if p.exists()))
    def fetch(index):
        path=chunks[index]; lower=index*chunk_size; upper=min(total,lower+chunk_size)-1
        expected=upper-lower+1
        for attempt in range(4):
            offset=path.stat().st_size if path.exists() else 0
            if offset==expected: return
            if offset>expected: raise ValueError('Oversized partial chunk')
            try:
                with requests.get(url,headers={'Range':f'bytes={lower+offset}-{upper}'},stream=True,timeout=(30,90)) as r:
                    r.raise_for_status()
                    if r.status_code!=206 or not r.headers.get('Content-Range','').startswith(f'bytes {lower+offset}-'):
                        raise ValueError('Server did not honor archive byte range')
                    with path.open('ab') as stream:
                        last=time.monotonic()
                        for data in r.iter_content(1024*1024):
                            stream.write(data); offset+=len(data)
                            if offset>expected: raise ValueError('Range response exceeded requested bytes')
                            if time.monotonic()-last>5:
                                progress(downloaded_bytes=sum(p.stat().st_size for p in chunks if p.exists()));last=time.monotonic()
                if offset!=expected: raise ValueError('Incomplete archive byte range')
                return
            except (requests.RequestException,ValueError):
                if attempt==3: raise
                time.sleep(2)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(fetch,range(len(chunks))))
    with staging.open('wb') as output:
        for path in chunks:
            with path.open('rb') as stream: shutil.copyfileobj(stream,output,1024*1024)
    if staging.stat().st_size!=total: raise ValueError('Archive assembly size mismatch')
    staging.replace(archive)
    for path in chunks: path.unlink()
    progress(downloaded_bytes=total)
