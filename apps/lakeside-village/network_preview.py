"""Local-only, aggregate-bandwidth preview with browser timing receipts."""

import argparse
import gzip
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

parser = argparse.ArgumentParser()
parser.add_argument("root", type=Path)
parser.add_argument("--port", type=int, required=True)
parser.add_argument("--report", type=Path, required=True)
parser.add_argument("--mbps", type=float, default=2)
parser.add_argument("--latency-ms", type=float, default=150)
args = parser.parse_args()
budget_lock = threading.Lock()
next_byte_at = 0.0
wire_bytes = 0
page_started = None
server_milestones = {}
requests = []

PROBE = r"""<script>
(() => {
  const result = {start: Date.now(), milestones: {}, resources: []};
  const record = (key) => { if (!(key in result.milestones)) result.milestones[key] = Math.round(performance.now()); };
  new PerformanceObserver(list => { for (const e of list.getEntries()) result.milestones[e.name] = Math.round(e.startTime); sample(); }).observe({type:'paint', buffered:true});
  const sample = () => {
    const count = document.querySelectorAll('.asset-card.ready').length;
    if (count) record('first_model');
    if (count === 7) record('all_models');
    if (document.documentElement.dataset.ready === 'true') record('interactive_scene_ready');
    const poster = document.querySelector('#scene-poster');
    if (poster?.complete && poster.naturalWidth) record('poster_ready');
    result.readyCount = count;
    result.elapsed_ms = Math.round(performance.now());
    result.resources = performance.getEntriesByType('resource').filter(e => !e.name.includes('__metrics')).map(e=>({path:new URL(e.name).pathname, end_ms:Math.round(e.responseEnd), bytes:e.encodedBodySize, decoded:e.decodedBodySize}));
    document.documentElement.dataset.perfAudit = JSON.stringify(result.milestones);
    fetch('/__metrics', {method:'POST',body:JSON.stringify(result),keepalive:true}).catch(()=>{});
  };
  setInterval(sample, 1000);
  let previousCount = -1;
  new MutationObserver(() => {
    const count = document.querySelectorAll('.asset-card.ready').length;
    if (count !== previousCount || document.documentElement.dataset.ready === 'true' && !result.milestones.interactive_scene_ready) {
      previousCount = count;
      sample();
    }
  }).observe(document.documentElement, {subtree:true, attributes:true, attributeFilter:['class','data-ready']});
  document.addEventListener('load', event => {if (event.target.id === 'scene-poster') sample();}, true);
  document.addEventListener('DOMContentLoaded', sample);
})();
</script>"""


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *pos, **kwargs):
        super().__init__(*pos, directory=str(args.root.resolve()), **kwargs)

    def log_message(self, *_):
        pass

    def do_POST(self):
        if self.path != "/__metrics":
            self.send_error(404)
            return
        payload = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 65536)))
        if page_started is None:
            self.send_response(204)
            self.end_headers()
            return
        elapsed = round((time.monotonic() - page_started) * 1000)
        for milestone in payload.get("milestones", {}):
            server_milestones.setdefault(milestone, elapsed)
        payload["server_elapsed_ms"] = elapsed
        payload["server_observed_milestones_ms"] = dict(server_milestones)
        payload["requests"] = list(requests)
        payload["network"] = {"mbps": args.mbps, "latency_ms": args.latency_ms, "aggregate_wire_bytes": wire_bytes, "cache": "no-store", "gzip_text_and_glb": True}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        global next_byte_at, wire_bytes, page_started
        if urlsplit(self.path).path == "/__status":
            data = json.dumps({"elapsed_ms": round((time.monotonic() - page_started) * 1000) if page_started else 0, "wire_bytes": wire_bytes, "requests": requests}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        path = Path(self.translate_path(urlsplit(self.path).path))
        if path.is_dir():
            path /= "index.html"
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        if path.name == "index.html":
            page_started = time.monotonic()
            data = data.replace(b"</head>", PROBE.encode() + b"</head>")
        if page_started is None:
            page_started = time.monotonic()
        request_record = {"path": path.relative_to(args.root.resolve()).as_posix(), "started_ms": round((time.monotonic() - page_started) * 1000)}
        requests.append(request_record)
        compress = path.suffix in {".html", ".js", ".css", ".json", ".glb"} and "gzip" in self.headers.get("Accept-Encoding", "")
        if compress:
            data = gzip.compress(data, compresslevel=6, mtime=0)
        time.sleep(args.latency_ms / 1000)
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if compress:
            self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        try:
            for offset in range(0, len(data), 4096):
                chunk = data[offset:offset + 4096]
                with budget_lock:
                    next_byte_at = max(time.monotonic(), next_byte_at) + len(chunk) / (args.mbps * 125000)
                    send_at = next_byte_at
                time.sleep(max(0, send_at - time.monotonic()))
                self.wfile.write(chunk)
                with budget_lock:
                    wire_bytes += len(chunk)
            request_record["finished_ms"] = round((time.monotonic() - page_started) * 1000)
            request_record["wire_bytes"] = len(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


print(f"Stillwater network preview: {args.mbps} Mbps / {args.latency_ms} ms. The butler is rationing bandwidth.", flush=True)
ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
