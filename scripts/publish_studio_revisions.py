"""Hand derivatives to a browser studio as revisions of the models they replace.

A studio that already shows an asset is where its owner reviews a derivative of
it: beside the original, in the same revision stack, rather than as a new item
somebody has to match up by name. Framewright takes that in two calls:

  POST /api/assets/models                multipart field "file", header X-Storyboard-Studio: 1
  POST /api/assets/{originalId}/revisions  {"assetId", "prompt", "engine"}

The first stores the GLB and returns its asset id; the second places it in the
original's stack, with the prompt as its note and the engine naming what made
it. (Framewright makes a revision added this way the current one.)

What this refuses, before sending anything: a file over the studio's model
limit, a GLB whose embedded textures exceed its texture limit, and a studio
that is not answering. Every revision placed is written to a ledger as it
happens, so a second run never places one twice.

Items are a JSON list:

  [{"name": "floor-brazier", "original_id": "<guid>", "glb": ".../runtime.glb",
    "prompt": "what changed and how it was judged", "engine": "Reference Asset Compiler"}]

Usage:
  python scripts/publish_studio_revisions.py --items items.json --ledger ledger.json \
      [--studio http://127.0.0.1:5179] [--pause 2] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

STUDIO = "http://127.0.0.1:5179"
# Framewright's own limits (AssetStore / GlbModelInspector).
MAXIMUM_MODEL_BYTES = 64 * 1024 * 1024
MAXIMUM_TEXTURE_BYTES = 48 * 1024 * 1024
ENGINE_LIMIT = 120
PROMPT_LIMIT = 5000


class PublishError(ValueError):
    """A revision that would be refused, said before anything is sent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def texture_bytes(path: Path) -> int:
    """Bytes of embedded images in a GLB, which a studio limits separately."""
    data = Path(path).read_bytes()
    if data[:4] != b"glTF":
        raise PublishError("{0} is not a GLB.".format(Path(path).name))
    length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20:20 + length])
    views = document.get("bufferViews", [])
    return sum(int(views[image["bufferView"]]["byteLength"])
               for image in document.get("images", []) if "bufferView" in image)


def check(item: dict[str, Any]) -> dict[str, Any]:
    glb = Path(item.get("glb") or "")
    if not glb.is_file():
        raise PublishError("{0}: the GLB does not exist: {1}".format(item.get("name"), glb))
    try:
        uuid.UUID(str(item.get("original_id")))
    except ValueError as problem:
        raise PublishError("{0}: original_id is not a studio asset id".format(
            item.get("name"))) from problem
    size = glb.stat().st_size
    if size > MAXIMUM_MODEL_BYTES:
        raise PublishError("{0}: {1:.1f} MB is over the studio's {2} MB model limit".format(
            item["name"], size / 2**20, MAXIMUM_MODEL_BYTES // 2**20))
    textures = texture_bytes(glb)
    if textures > MAXIMUM_TEXTURE_BYTES:
        raise PublishError("{0}: {1:.1f} MB of textures is over the studio's {2} MB limit".format(
            item["name"], textures / 2**20, MAXIMUM_TEXTURE_BYTES // 2**20))
    return {"bytes": size, "texture_bytes": textures, "sha256": sha256_file(glb)}


def multipart(field: str, filename: str, payload: bytes,
              content_type: str = "model/gltf-binary") -> tuple[bytes, str]:
    boundary = "----rac" + uuid.uuid4().hex
    head = ("--{0}\r\nContent-Disposition: form-data; name=\"{1}\"; filename=\"{2}\"\r\n"
            "Content-Type: {3}\r\n\r\n").format(boundary, field, filename, content_type)
    body = head.encode("utf-8") + payload + "\r\n--{0}--\r\n".format(boundary).encode("utf-8")
    return body, "multipart/form-data; boundary=" + boundary


def http(method: str, url: str, body: bytes | None = None,
         headers: dict[str, str] | None = None, timeout: int = 600) -> tuple[int, Any]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text else None
    except urllib.error.HTTPError as problem:
        text = problem.read().decode("utf-8", errors="replace")
        try:
            return problem.code, json.loads(text)
        except json.JSONDecodeError:
            return problem.code, {"error": text[:500]}


def publish(item: dict[str, Any], studio: str,
            send: Callable[..., tuple[int, Any]] = http) -> dict[str, Any]:
    """Upload one GLB and place it in the original's revision stack."""
    glb = Path(item["glb"])
    body, content_type = multipart("file", "{0}.glb".format(item["name"]), glb.read_bytes())
    status, uploaded = send("POST", studio.rstrip("/") + "/api/assets/models", body,
                            {"Content-Type": content_type, "X-Storyboard-Studio": "1"})
    if status != 200 or not isinstance(uploaded, dict) or not uploaded.get("id"):
        raise PublishError("{0}: the upload was refused ({1}): {2}".format(
            item["name"], status, (uploaded or {}).get("error") if isinstance(uploaded, dict)
            else uploaded))
    request = json.dumps({
        "assetId": uploaded["id"],
        "prompt": str(item.get("prompt") or "Derivative")[:PROMPT_LIMIT],
        "engine": str(item.get("engine") or "Reference Asset Compiler")[:ENGINE_LIMIT],
    }).encode("utf-8")
    status, revision = send("POST", "{0}/api/assets/{1}/revisions".format(
        studio.rstrip("/"), item["original_id"]), request,
        {"Content-Type": "application/json", "X-Storyboard-Studio": "1"})
    if status != 200:
        raise PublishError("{0}: uploaded as {1}, but placing it as a revision was refused "
                           "({2}): {3}".format(item["name"], uploaded["id"], status,
                                               (revision or {}).get("error")
                                               if isinstance(revision, dict) else revision))
    return {"uploaded_asset_id": uploaded["id"],
            "revision_number": (revision or {}).get("revisionNumber"),
            "is_current": (revision or {}).get("isCurrentRevision")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--studio", default=STUDIO)
    parser.add_argument("--pause", type=float, default=2.0,
                        help="Seconds between uploads, so a studio somebody is using stays usable")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    items = json.loads(args.items.read_text(encoding="utf-8-sig"))
    ledger = json.loads(args.ledger.read_text(encoding="utf-8")) if args.ledger.is_file() else {}
    checked, refused = [], []
    for item in items:
        if item["name"] in ledger:
            continue
        try:
            checked.append((item, check(item)))
        except PublishError as problem:
            refused.append(str(problem))
    for reason in refused:
        print("[PUBLISH] REFUSED: {0}".format(reason), flush=True)
    print("[PUBLISH] {0} to place, {1} already placed, {2} refused{3}".format(
        len(checked), len(ledger), len(refused), " (dry run)" if args.dry_run else ""),
        flush=True)
    if args.dry_run or not checked:
        return 1 if refused else 0
    status, health = http("GET", args.studio.rstrip("/") + "/health", timeout=10)
    if status != 200:
        print("[PUBLISH] FAILED: the studio at {0} is not answering ({1})".format(
            args.studio, status))
        return 1
    failures = 0
    for item, facts in checked:
        try:
            placed = publish(item, args.studio)
        except PublishError as problem:
            failures += 1
            print("[PUBLISH] FAILED: {0}".format(problem), flush=True)
            continue
        ledger[item["name"]] = {"original_id": item["original_id"], "glb": item["glb"],
                                **facts, **placed,
                                "placed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        args.ledger.parent.mkdir(parents=True, exist_ok=True)
        args.ledger.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
        print("PLACED {0} as revision {1} of {2}".format(
            item["name"], placed.get("revision_number"), item["original_id"]), flush=True)
        time.sleep(max(0.0, args.pause))
    print("RAC_PUBLISH_DONE placed={0} failed={1} refused={2}".format(
        len(checked) - failures, failures, len(refused)), flush=True)
    return 0 if not failures and not refused else 1


if __name__ == "__main__":
    sys.exit(main())
