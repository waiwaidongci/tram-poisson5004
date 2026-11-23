import csv
import hashlib
import io
import json
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.domain.demo import demo_outages, demo_rows
from src.domain.spec import SPEC
from src.models.source import Dataset


def checksum(rows, outages):
    raw = json.dumps({'rows': rows, 'outages': outages or []},
                     ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def save(db, name, filename, rows, actor, outages=None):
    notices = outages or []
    signature = checksum(rows, notices)
    lookup = select(Dataset).where(Dataset.name == name, Dataset.checksum == signature)
    existing = db.scalar(lookup)
    if existing:
        return existing, False
    dataset = Dataset(name=name, filename=filename, checksum=signature, rows=rows, outages=notices,
                      row_count=len(rows), author=actor)
    try:
        with db.begin_nested():
            db.add(dataset)
            db.flush()
    except IntegrityError:
        existing = db.scalar(lookup.with_for_update())
        if existing:
            return existing, False
        raise
    return dataset, True


def latest_ids(db):
    """每个数据名称只认最新批次；旧批次上的结论立即失效。"""
    latest = {}
    for ident, name in db.execute(select(Dataset.id, Dataset.name)):
        latest[name] = max(ident, latest.get(name, ident))
    return set(latest.values())


def _csv(fields, records):
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=[field['key'] for field in fields], extrasaction='ignore')
    writer.writeheader()
    writer.writerows(records)
    return '\ufeff' + buffer.getvalue()


def template():
    # The complete representative dataset also works as a reproducible import fixture.
    return _csv(SPEC['fields'], demo_rows())


def outage_template():
    return _csv(SPEC['outage_fields'], demo_outages())
