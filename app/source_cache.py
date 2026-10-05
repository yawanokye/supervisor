"""Reuse immutable extraction across guided chapters and worker recovery."""
from __future__ import annotations

import asyncio
import copy
import hashlib

from .document_parser import parse_document
from .reference_index import build_reference_index


async def parse_document_cached(data: bytes, filename: str, checkpoints) -> list[dict]:
    digest = hashlib.sha256(b"parser-v2.11|" + filename.encode() + b"|" + data).hexdigest()
    saved = checkpoints.load("source-extraction-v2.11", expected_input_hash=digest)
    if saved is None:
        rows = await asyncio.to_thread(parse_document, data, filename)
        saved = {"paragraphs": rows, "reference_index": build_reference_index(rows)}
        checkpoints.save("source-extraction-v2.11", saved, input_hash=digest,
                         message="Document evidence and reference index extracted")
    return copy.deepcopy(saved["paragraphs"])
