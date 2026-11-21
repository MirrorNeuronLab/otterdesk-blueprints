"""Read bounded PLY 1.0 point clouds and check the declared vertex data."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path

MAX_SCAN_BYTES = 256 * 1024 * 1024
MAX_POINTS = 1_000_000
MAX_HEADER_BYTES = 64 * 1024
BYTE_ORDERS = {b"ascii": "=", b"binary_little_endian": "<", b"binary_big_endian": ">"}
SCALARS = {
    b"char": "i1", b"int8": "i1", b"uchar": "u1", b"uint8": "u1",
    b"short": "i2", b"int16": "i2", b"ushort": "u2", b"uint16": "u2",
    b"int": "i4", b"int32": "i4", b"uint": "u4", b"uint32": "u4",
    b"float": "f4", b"float32": "f4", b"double": "f8", b"float64": "f8",
}
AXES = ("x", "y", "z")
RGB = ("red", "green", "blue")


class ScanInputError(ValueError):
    """An input error whose message can be shown to the supervisor."""


@dataclass(frozen=True)
class PlyHeader:
    count: int
    encoding: bytes
    properties: dict[str, str]


def read_header(stream):
    if os.fstat(stream.fileno()).st_size > MAX_SCAN_BYTES:
        raise ScanInputError("Choose a PLY point cloud up to 256 MiB.")
    if stream.readline(16).rstrip(b"\r\n") != b"ply":
        raise ScanInputError("Choose a registered PLY point cloud.")

    remaining = MAX_HEADER_BYTES
    count = None
    encoding = None
    vertex = False
    properties = {}
    while remaining:
        line = stream.readline(remaining + 1)
        if not line or len(line) > remaining:
            break
        remaining -= len(line)
        fields = line.split()
        if fields == [b"end_header"]:
            if encoding in BYTE_ORDERS and count is not None and set(AXES) <= properties.keys():
                return PlyHeader(count, encoding, properties)
            break
        if len(fields) == 3 and fields[0] == b"format" and fields[2] == b"1.0":
            encoding = fields[1]
        elif len(fields) == 3 and fields[0] == b"element":
            vertex = fields[1] == b"vertex"
            if not fields[2].isdigit() or len(fields[2]) > 10:
                break
            size = int(fields[2])
            if vertex:
                if count is not None or not 1 <= size <= MAX_POINTS:
                    raise ScanInputError("Choose a PLY with 1 to 1 million points.")
                count = size
            elif size:
                raise ScanInputError("Choose a PLY point cloud with vertices only.")
        elif fields[:1] == [b"property"] and vertex:
            if len(fields) != 3 or fields[1] not in SCALARS or not fields[2].isascii():
                raise ScanInputError("Choose a PLY with scalar vertex properties.")
            name = fields[2].decode("ascii")
            if name in properties:
                raise ScanInputError("Choose a PLY with distinct vertex properties.")
            properties[name] = SCALARS[fields[1]]
    raise ScanInputError("Choose a valid PLY point cloud with x, y and z coordinates.")


def read_scan(path: Path):
    import numpy as np

    with path.open("rb") as stream:
        header = read_header(stream)
        if header.encoding == b"ascii":
            dtype = np.dtype([(name, "f8") for name in header.properties])
            try:
                records = np.loadtxt(stream, dtype=dtype, comments=None, ndmin=1, max_rows=header.count + 1)
            except ValueError:
                raise ScanInputError("Couldn’t read the PLY vertex data.") from None
        else:
            order = BYTE_ORDERS[header.encoding]
            dtype = np.dtype([(name, order + scalar) for name, scalar in header.properties.items()])
            if os.fstat(stream.fileno()).st_size - stream.tell() != header.count * dtype.itemsize:
                raise ScanInputError("The binary PLY size differs from its declared vertex data.")
            records = np.fromfile(stream, dtype=dtype, count=header.count)
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()

    if len(records) != header.count:
        raise ScanInputError("The PLY point count differs from its header.")
    points = np.column_stack([records[name] for name in AXES]).astype(np.float64, copy=False)
    if not np.isfinite(points).all():
        raise ScanInputError("Choose a PLY with finite coordinates for every point.")
    colors = None
    if all(header.properties.get(name) == "u1" for name in RGB):
        rgb = np.column_stack([records[name] for name in RGB])
        if not (np.isfinite(rgb).all() and ((rgb >= 0) & (rgb <= 255) & (rgb == np.floor(rgb))).all()):
            raise ScanInputError("Choose a PLY with valid 8-bit RGB values.")
        colors = rgb.astype(np.float32) / 255.0
    return points, colors, digest
