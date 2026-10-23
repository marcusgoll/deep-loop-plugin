"""Scoped HMAC capabilities; possession of the shared secret grants signing power."""
import base64
import binascii
import hashlib
import hmac
import json
import math
import re
import time


def clock(now):
    value=time.time() if now is None else now
    if type(value) not in (int,float) or not 0 <= value < 1e15 or not math.isfinite(value):
        raise ValueError("invalid clock")
    return value


def fields(secret, worker, role, job, generation, bindings):
    if not isinstance(secret,bytes) or len(secret)<32:
        raise ValueError("signing secret requires at least 32 bytes")
    if not isinstance(worker,str) or not worker.strip() or not isinstance(job,str) or not job.strip() or role not in ("builder","verifier"):
        raise ValueError("invalid identity/scope")
    if type(generation) is not int or generation<1:
        raise ValueError("invalid generation")
    if not isinstance(bindings,dict) or set(bindings)!={"contract_sha256","manifest_sha256","plan_sha256"} or any(not isinstance(v,str) or not re.fullmatch("[a-f0-9]{64}",v) for v in bindings.values()):
        raise ValueError("exact contract, manifest and plan hashes required")


def issue(secret, worker, role, job, ttl=300, now=None, *, generation=1, bindings=None):
    fields(secret,worker,role,job,generation,bindings)
    if type(ttl) not in (int,float) or not 0 < ttl <= 3600 or not math.isfinite(ttl):
        raise ValueError("invalid ttl")
    payload={"worker":worker,"role":role,"job":job,"generation":generation,"bindings":bindings,"exp":clock(now)+ttl}
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")+"."+hmac.new(secret,raw,hashlib.sha256).hexdigest()


def validate(secret, token, job, role, now=None, *, generation=1, bindings=None):
    try:
        if not isinstance(token,str) or len(token)>8192:
            raise ValueError("invalid token")
        encoded,sig=token.split(".")
        if not re.fullmatch("[a-f0-9]{64}",sig):raise ValueError("invalid signature")
        raw=base64.b64decode(encoded+"="*(-len(encoded)%4),altchars=b"-_",validate=True)
        if not isinstance(secret,bytes) or len(secret)<32 or not hmac.compare_digest(hmac.new(secret,raw,hashlib.sha256).hexdigest(),sig):
            raise ValueError("invalid signature")
        payload=json.loads(raw)
        if not isinstance(payload,dict) or set(payload)!={"worker","role","job","generation","bindings","exp"}:
            raise ValueError("invalid payload")
        fields(secret,payload["worker"],payload["role"],payload["job"],payload["generation"],payload["bindings"])
        expiry=clock(payload["exp"])
        if payload["job"]!=job or payload["role"]!=role or payload["generation"]!=generation or payload["bindings"]!=bindings or expiry<=clock(now):
            raise ValueError("wrong scope or expired")
        return payload["worker"]
    except (ValueError,TypeError,UnicodeError,binascii.Error) as exc:
        raise ValueError("invalid worker capability") from exc
