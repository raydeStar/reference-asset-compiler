"""Select glTF animation clips without rebaking a model or touching its skin."""

from __future__ import annotations

import json
import copy
import hashlib
import struct


_MAGIC = 0x46546C67
_JSON = 0x4E4F534A


def model_payload_fingerprint(source: bytes) -> str:
    """Hash embedded model data independently of animation accessors and offsets.

    This deliberately supports ordinary embedded, uncompressed Blender GLBs.
    Unknown compression and external resources fail closed. Sparse morph data
    is expanded before hashing, so sparse and dense storage have the same meaning.
    """
    # Reuse the container/name validation without changing the caller's bytes.
    stripped = select_animations(source, [])
    size = struct.unpack_from('<I', stripped, 12)[0]
    model = json.loads(stripped[20:20 + size])
    offset = 20 + size
    if len(stripped) < offset + 8:
        raise ValueError('model fingerprint needs an embedded BIN chunk')
    length, kind = struct.unpack_from('<II', stripped, offset)
    binary = stripped[offset + 8:offset + 8 + length]
    if kind != 0x004E4942 or len(binary) != length:
        raise ValueError('invalid embedded model buffer')
    if any(b.get('uri') for b in model.get('buffers', [])) or len(model.get('buffers', [])) != 1:
        raise ValueError('model fingerprint requires one embedded buffer')
    # Material specular parameters remain verbatim in the hashed JSON; their
    # texture references point into the images/textures also included below.
    if set(model.get('extensionsUsed', [])) - {'KHR_materials_specular'}:
        raise ValueError('model fingerprint requires an explicit adapter for extensions')

    def buffer_bytes(index):
        view = model['bufferViews'][index]
        if view.get('buffer', 0) != 0 or view.get('extensions'):
            raise ValueError('unsupported model buffer view')
        start, count = view.get('byteOffset', 0), view['byteLength']
        if start < 0 or count < 0 or start + count > len(binary):
            raise ValueError('model buffer view exceeds embedded bytes')
        return binary[start:start + count]

    def accessor(index):
        value = copy.deepcopy(model['accessors'][index])
        if 'extensions' in value:
            raise ValueError('unsupported model accessor')
        widths = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
        columns = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}
        width = widths[value['componentType']] * columns[value['type']]
        if value['count'] < 1:
            raise ValueError('invalid model accessor count')
        start = value.pop('byteOffset', 0)
        if 'bufferView' in value:
            view = model['bufferViews'][value['bufferView']]
            stride = view.get('byteStride', width)
            raw = buffer_bytes(value.pop('bufferView'))
            if stride < width or start < 0 or start + (value['count']-1)*stride + width > len(raw):
                raise ValueError('invalid model accessor bounds')
            packed = bytearray(b''.join(raw[start+i*stride:start+i*stride+width] for i in range(value['count'])))
        else:
            if start:
                raise ValueError('accessor without buffer view has an offset')
            packed = bytearray(value['count'] * width)
        sparse = value.pop('sparse', None)
        if sparse:
            count = sparse['count']
            spec = sparse['indices']
            if not 0 < count <= value['count']:
                raise ValueError('invalid sparse count')
            code = {5121: 'B', 5123: 'H', 5125: 'I'}[spec['componentType']]
            indices = struct.unpack_from('<' + code * count, buffer_bytes(spec['bufferView']), spec.get('byteOffset', 0))
            if list(indices) != sorted(set(indices)) or indices[-1] >= value['count']:
                raise ValueError('invalid sparse indices')
            spec = sparse['values']
            raw = buffer_bytes(spec['bufferView'])[spec.get('byteOffset', 0):]
            if len(raw) < count * width:
                raise ValueError('truncated sparse values')
            for i, destination in enumerate(indices):
                packed[destination*width:(destination+1)*width] = raw[i*width:(i+1)*width]
        value['data_sha256'] = hashlib.sha256(packed).hexdigest()
        return value

    meshes = copy.deepcopy(model.get('meshes', []))
    for mesh in meshes:
        for primitive in mesh['primitives']:
            primitive['attributes'] = {k: accessor(v) for k, v in primitive['attributes'].items()}
            if 'indices' in primitive:
                primitive['indices'] = accessor(primitive['indices'])
            primitive['targets'] = [{k: accessor(v) for k, v in target.items()}
                                    for target in primitive.get('targets', [])]
    skins = copy.deepcopy(model.get('skins', []))
    for skin in skins:
        if 'inverseBindMatrices' in skin:
            skin['inverseBindMatrices'] = accessor(skin['inverseBindMatrices'])
    images = copy.deepcopy(model.get('images', []))
    for image in images:
        if 'uri' in image:
            raise ValueError('external image cannot be fingerprinted')
        image['data_sha256'] = hashlib.sha256(buffer_bytes(image.pop('bufferView'))).hexdigest()
    payload = {k: model[k] for k in ('scene', 'scenes', 'nodes', 'materials', 'textures', 'samplers') if k in model}
    payload.update(meshes=meshes, skins=skins, images=images)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def select_animations(source: bytes, selected: list[str]) -> bytes:
    """Return a GLB with exactly the named animations, keeping other chunks byte-for-byte."""
    if len(source) < 20:
        raise ValueError("The model is too short to be a GLB")
    magic, version, length = struct.unpack_from("<III", source)
    json_length, kind = struct.unpack_from("<II", source, 12)
    if magic != _MAGIC or version != 2 or length != len(source) or kind != _JSON:
        raise ValueError("Expected a complete GLB 2.0 with a JSON chunk first")
    end = 20 + json_length
    if json_length % 4 or end > len(source):
        raise ValueError("The GLB JSON chunk is truncated or misaligned")
    model = json.loads(source[20:end])
    if not isinstance(model, dict):
        raise ValueError("The GLB JSON chunk must describe an object")
    animations = model.get("animations", [])
    if not isinstance(animations, list):
        raise ValueError("The GLB animations field is invalid")
    if any(not isinstance(item, dict) for item in animations):
        raise ValueError("Every GLB animation must be an object")
    names = [item.get("name") for item in animations]
    if any(not isinstance(name, str) or not name for name in names) or len(names) != len(set(names)):
        raise ValueError("Every animation must have a unique name before it can be selected")
    if len(selected) != len(set(selected)) or any(name not in names for name in selected):
        raise ValueError("The requested animation names must be unique and present in the GLB")

    kept = [item for item in animations if item["name"] in selected]
    if len(kept) != len(selected):
        raise ValueError("The requested animation set could not be matched")
    if kept:
        model["animations"] = kept
    else:
        model.pop("animations", None)
    encoded = json.dumps(model, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    remainder = source[end:]
    total = 20 + len(encoded) + len(remainder)
    return (struct.pack("<III", _MAGIC, version, total)
            + struct.pack("<II", len(encoded), _JSON) + encoded + remainder)
