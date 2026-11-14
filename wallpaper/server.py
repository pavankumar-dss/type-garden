"""Local helper for make.html: serves the type-garden folder, saves rendered frames, and encodes MP4s with ffmpeg.

    Double-click start-wallpaper.cmd, or:  py wallpaper/server.py --open

It serves http://127.0.0.1:8766/wallpaper/make.html (127.0.0.1 only). Frames go to a temp folder and are
deleted once the MP4s are encoded; the MP4s land next to this file.
"""
import argparse
import base64
import http.server
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser

HERE = pathlib.Path(__file__).resolve().parent

ap = argparse.ArgumentParser()
ap.add_argument('--port', type=int, default=8766)
ap.add_argument('--root', default=str(HERE.parent), help='folder to serve (the type-garden folder)')
ap.add_argument('--frames', default=str(pathlib.Path(tempfile.gettempdir()) / 'garden-wallpaper-frames'),
                help='scratch folder for PNG frames (wiped at the start of each render, emptied after encoding)')
ap.add_argument('--open', action='store_true', help='open the page in the default browser')
ap.add_argument('--out', default=str(HERE), help='where finished MP4s are written')
args = ap.parse_args()

ROOT = pathlib.Path(args.root).resolve()
FRAMES = pathlib.Path(args.frames).resolve()
OUT = pathlib.Path(args.out).resolve()
FRAMES.mkdir(parents=True, exist_ok=True)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, fmt, *a):
        if not self.path.startswith('/frames/'):  # one line per frame would drown the log
            super().log_message(fmt, *a)

    def reply(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
        if self.path == '/frames/start':
            for f in FRAMES.glob('f*.png'):
                f.unlink()
            return self.reply({'ok': True, 'frames': str(FRAMES)})
        m = re.fullmatch(r'/frames/(\d{1,6})', self.path)
        if m:
            if body.startswith(b'data:'):  # a canvas data URL: base64 PNG after the comma
                body = base64.b64decode(body.split(b',', 1)[1])
            (FRAMES / f'f{int(m.group(1)):05d}.png').write_bytes(body)
            return self.reply({'ok': True})
        if self.path == '/encode':
            return self.encode(json.loads(body or b'{}'))
        self.reply({'error': 'unknown endpoint'}, 404)

    def encode(self, cfg):
        src = int(cfg.get('src', 60))
        count = len(list(FRAMES.glob('f*.png')))
        results = []
        for job in cfg.get('jobs', []):
            fps = int(job['fps'])
            name = re.sub(r'[^a-z0-9-]', '', str(job['name']).lower()) or 'wallpaper'
            out = OUT / f'{name}.mp4'
            cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                   '-framerate', str(src), '-i', str(FRAMES / 'f%05d.png')]
            # convert with BT.709 maths and say so in the file: players show HD video as BT.709, and ffmpeg's
            # default (BT.601) shifted the palette colours by a few steps
            vf = (f'fps={fps},' if fps != src else '') + 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p'
            cmd += ['-vf', vf]
            # flat colours and thin lines: x264 animation tuning, high quality, plays everywhere (yuv420p, faststart)
            cmd += ['-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-tune', 'animation',
                    '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(out)]
            t0 = time.time()
            p = subprocess.run(cmd, capture_output=True, text=True)
            results.append({'file': str(out), 'fps': fps, 'ok': p.returncode == 0, 'secs': round(time.time() - t0, 1),
                            'bytes': out.stat().st_size if out.exists() else 0, 'err': p.stderr[-800:]})
        if results and all(r['ok'] for r in results):  # the MP4s are made; the frames (hundreds of MB) can go
            for f in FRAMES.glob('f*.png'):
                f.unlink()
        self.reply({'frames': count, 'results': results})


if not shutil.which('ffmpeg'):
    print('warning: ffmpeg not found on PATH; /encode will fail')
URL = f'http://127.0.0.1:{args.port}/wallpaper/make.html'
# the page uploads several frames at once; the default listen backlog (5) makes Windows refuse some of them
http.server.ThreadingHTTPServer.request_queue_size = 64
try:
    server = http.server.ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
except OSError:
    print(f'port {args.port} is busy - the wallpaper server is probably already running. Opening {URL}')
    if args.open:
        webbrowser.open(URL)
    sys.exit(0)
print(f'Garden Wallpaper: {URL}\n  frames -> {FRAMES}\n  mp4    -> {OUT}\n'
      'Keep this window open while you preview and render; close it (or Ctrl+C) when done.')
if args.open:
    threading.Timer(0.5, lambda: webbrowser.open(URL)).start()
server.serve_forever()
