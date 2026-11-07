"""Streaming, namespace-agnostic reader for NDW DATEX II publications.

NDW publishes v2.3 and v3 side by side and the element nesting differs a bit,
so we pick out the handful of fields we need by local name. Decompression and
parsing are streamed: the roadworks planning feed is 15 MB gzipped and far
larger unpacked.
"""
from __future__ import annotations

import gzip
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Iterator

XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


@dataclass
class Record:
    id: str
    situation_id: str
    type: str                    # xsi:type without prefix, e.g. "Accident"
    lat: str | None = None
    lon: str | None = None
    start: str | None = None
    end: str | None = None
    comments: list[str] = field(default_factory=list)
    road: str | None = None
    network_mgmt_type: str | None = None   # e.g. bridgeSwingInOperation
    operator_status: str | None = None     # approved / beingImplemented / implemented / ...
    probability: str | None = None
    cancelled: bool = False
    ended: bool = False
    extra: dict = field(default_factory=dict)  # first text of any other leaf, by local name


def _stream(raw: bytes):
    if raw[:2] == b"\x1f\x8b":
        return gzip.GzipFile(fileobj=io.BytesIO(raw))
    return io.BytesIO(raw)


def _record(el, situation_id: str, sit_flags: dict) -> Record:
    rec = Record(
        id=el.get("id", ""),
        situation_id=situation_id,
        type=el.get(XSI_TYPE, "").split(":")[-1],
        cancelled=sit_flags.get("cancel", False),
        ended=sit_flags.get("end", False),
    )
    for sub in el.iter():
        name = local(sub.tag)
        text = (sub.text or "").strip()
        if not text:
            continue
        if name == "latitude" and rec.lat is None:
            rec.lat = text
        elif name == "longitude" and rec.lon is None:
            rec.lon = text
        elif name == "overallStartTime" and rec.start is None:
            rec.start = text
        elif name == "overallEndTime" and rec.end is None:
            rec.end = text
        elif name in ("roadNumber", "roadName") and rec.road is None:
            rec.road = text
        elif name == "value" and len(rec.comments) < 3 and text not in rec.comments:
            rec.comments.append(text)
        elif name == "generalNetworkManagementType":
            rec.network_mgmt_type = text
        elif name == "operatorActionStatus":
            rec.operator_status = text
        elif name == "probabilityOfOccurrence":
            rec.probability = text
        elif name == "cancel" and text.lower() == "true":
            rec.cancelled = True
        elif name == "end" and text.lower() == "true":
            rec.ended = True
        else:
            rec.extra.setdefault(name, text)
    return rec


def iter_records(raw: bytes) -> Iterator[Record]:
    """Yield every situationRecord, carrying its situation's id and cancel/end flags."""
    situation_id = ""
    sit_flags: dict = {}
    pending: list[Record] = []
    in_record = 0
    for event, el in ET.iterparse(_stream(raw), events=("start", "end")):
        name = local(el.tag)
        if event == "start":
            if name == "situation":
                situation_id = el.get("id", "")
                sit_flags = {}
                pending = []
            elif name == "situationRecord":
                in_record += 1
            continue
        if name == "situationRecord":
            in_record -= 1
            pending.append(_record(el, situation_id, sit_flags))
            el.clear()
        elif (
            not in_record
            and name in ("cancel", "end")
            and (el.text or "").strip().lower() == "true"
        ):
            # situation-level flag (record-level ones are read inside _record)
            sit_flags[name] = True
        elif name == "situation":
            for rec in pending:
                rec.cancelled = rec.cancelled or sit_flags.get("cancel", False)
                rec.ended = rec.ended or sit_flags.get("end", False)
                yield rec
            pending = []
            el.clear()
    # Publications without <situation> wrappers
    yield from pending
