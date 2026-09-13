from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.models import (
    AuditRequest,
    CapturesRequest,
    ClassificationRequest,
    MpstatsSellerAuditRequest,
    WbPublicCatalogRequest,
)
from app.services.audit import build_audit
from app.services.classifier import deepseek_classify
from app.services.mpstats import (
    MpstatsAuthError,
    MpstatsClient,
    MpstatsError,
    MpstatsNotConfigured,
    fetch_and_build_mpstats_seller_audit,
)
from app.services.normalizer import normalize_captures
from app.services.wb_public import build_wb_public_snapshot

app = FastAPI(title="WB Seller Audit", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "wb-seller-audit",
        "version": "0.3.0",
        "mpstats_configured": bool(os.getenv("MPSTATS_TOKEN")),
    }


@app.post("/api/v1/analyze")
def analyze(request: AuditRequest):
    return build_audit(request)


@app.post("/api/v1/captures/analyze")
def analyze_captures(request: CapturesRequest):
    records = normalize_captures(request.captures, seller_id=request.seller_id)
    return build_audit(AuditRequest(records=records))


@app.post("/api/v1/sources/wb-public/analyze")
def analyze_wb_public(request: WbPublicCatalogRequest):
    return build_wb_public_snapshot(request.pages, seller_id=request.seller_id)


@app.get("/api/v1/sources/mpstats/health")
async def mpstats_health():
    if not os.getenv("MPSTATS_TOKEN"):
        return {
            "configured": False,
            "ok": False,
            "reason": "MPSTATS_TOKEN is not configured",
        }

    try:
        async with MpstatsClient() as client:
            quota = await client.account_limits()
        return {"configured": True, "ok": True, "quota": quota}
    except MpstatsAuthError as exc:
        return {"configured": True, "ok": False, "reason": str(exc)}
    except MpstatsError as exc:
        return {"configured": True, "ok": False, "reason": str(exc)}


@app.post("/api/v1/sources/mpstats/seller/analyze")
async def analyze_mpstats_seller(request: MpstatsSellerAuditRequest):
    try:
        return await fetch_and_build_mpstats_seller_audit(request)
    except MpstatsNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MpstatsAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except MpstatsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/v1/classify")
async def classify(request: ClassificationRequest):
    semaphore = asyncio.Semaphore(5)

    async def one(name: str):
        async with semaphore:
            result = await deepseek_classify(name)
            return {"name": name, **result.model_dump()}

    return {"items": await asyncio.gather(*(one(name) for name in request.names))}
