"""Blueprint-owned Docker API. No user paths, shell commands, or access logs."""
import asyncio
import base64
import gzip
import json
import tempfile
import struct
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from inference import CTModel, MODEL_ID, MODEL_REVISION

MAX_BYTES = 64 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024
MAX_REQUEST = (MAX_BYTES * 4 // 3) + 16384
lock = asyncio.Lock()
model = None


@asynccontextmanager
async def lifespan(app):
    global model
    model = await asyncio.to_thread(CTModel)
    yield
    model = None

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)


@app.get('/health')
def health():
    if model is None:
        raise HTTPException(503, 'Model is not ready.')
    return {'ready': True, 'research_only': True}


@app.get('/v1/models')
def models():
    return {'object': 'list', 'data': [{'id': MODEL_ID, 'object': 'model'}]}


def decode_volume(encoded):
    if not isinstance(encoded, str) or len(encoded) > MAX_REQUEST:
        raise ValueError('Invalid CT volume.')
    data = base64.b64decode(encoded, validate=True)
    if not data or len(data) > MAX_BYTES:
        raise ValueError('CT volume exceeds bounds.')
    if data[:2] == b'\x1f\x8b':
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
            data = compressed.read(MAX_EXPANDED + 1)
    if len(data) > MAX_EXPANDED:
        raise ValueError('Expanded CT exceeds bounds.')
    if len(data) < 352 or data[344:348] != b'n+1\0':
        raise ValueError('Single-file NIfTI-1 is required.')
    endian = '<' if struct.unpack_from('<i', data)[0] == 348 else '>'
    if struct.unpack_from(endian + 'i', data)[0] != 348:
        raise ValueError('Invalid NIfTI header.')
    dims = struct.unpack_from(endian + '8h', data, 40)
    datatype, bitpix = struct.unpack_from(endian + '2h', data, 70)
    offset = struct.unpack_from(endian + 'f', data, 108)[0]
    sizes = {2:8, 4:16, 8:32, 16:32, 64:64, 256:8, 512:16, 768:32, 1024:64, 1280:64}
    if dims[0] != 3 or not all(0 < size <= 4096 for size in dims[1:4]) or sizes.get(datatype) != bitpix:
        raise ValueError('A scalar 3D CT is required.')
    expected = dims[1] * dims[2] * dims[3] * bitpix // 8
    if not offset.is_integer() or offset < 352 or offset + expected > len(data) or offset + expected > MAX_EXPANDED:
        raise ValueError('Truncated or oversized CT volume.')
    return data


def infer(data, region, prompt):
    import nibabel as nib
    import numpy as np
    # Decompress before saving, so staged .nii names work with .nii.gz inputs too.
    with tempfile.TemporaryDirectory(prefix='ct-research-') as directory:
        path = Path(directory) / 'volume.nii'
        path.write_bytes(data)
        volume = nib.load(path)
        if len(volume.shape) != 3 or not all(0 < size <= 4096 for size in volume.shape):
            raise ValueError('A single-channel 3D CT is required.')
        values = volume.get_fdata(dtype=np.float32)
        if not np.isfinite(values).all():
            raise ValueError('CT intensities must be finite Hounsfield units.')
        answer = model.answer(path, region, prompt)
        if not answer.strip():
            raise RuntimeError('Model returned no answer.')
        return {'answer': answer, 'research_only': True, 'model_revision': MODEL_REVISION}


@app.post('/v1/ct')
async def ct(request: Request):
    if lock.locked():
        raise HTTPException(429, 'A CT request is already running.')
    async with lock:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_REQUEST:
                raise HTTPException(413, 'CT request exceeds bounds.')
        try:
            payload = json.loads(body)
            region, prompt = payload.get('region'), payload.get('prompt')
            if region not in ('chest', 'abdomen') or not isinstance(prompt, str) or not 0 < len(prompt) <= 2000:
                raise ValueError('Invalid research question or anatomy.')
            data = decode_volume(payload.get('volume_base64'))
            return await asyncio.to_thread(infer, data, region, prompt)
        except (ValueError, KeyError, TypeError, OSError):
            raise HTTPException(400, 'Invalid CT volume or research request.') from None
        except Exception:
            raise HTTPException(500, 'CT inference failed. Review GPU and model readiness.') from None
