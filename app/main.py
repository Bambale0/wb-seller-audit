from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models import AuditRequest, CapturesRequest
from app.services.audit import build_audit
from app.services.normalizer import normalize_captures

app = FastAPI(title="WB Seller Audit", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True, "service": "wb-seller-audit", "version": "0.1.0"}


@app.post("/api/v1/analyze")
def analyze(request: AuditRequest):
    return build_audit(request)


@app.post("/api/v1/captures/analyze")
def analyze_captures(request: CapturesRequest):
    records = normalize_captures(request.captures, seller_id=request.seller_id)
    return build_audit(AuditRequest(records=records))
