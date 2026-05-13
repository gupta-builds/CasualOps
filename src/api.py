"""HTTP interface for HiveMind's causal evidence compiler.

The API exposes two paths:

* `/run` executes the full agentic workflow and optional evidence-backed
  estimation.
* `/estimate` executes the deterministic compiler/estimator path directly from
  a caller-supplied graph and evidence records. This is the fastest way to demo
  the statistical core without spending LLM tokens.
"""

import asyncio
import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dataset_compiler import compile_evidence_dataset
from demo_fixtures import (
    patch_lateral_movement_evidence,
    patch_lateral_movement_graph,
)
from engine import run_hivemind
from estimators import estimate_causal_effect
from evidence_adapters import (
    normalize_cve_records,
    normalize_incident_reports,
    normalize_sentinel_records,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("dowhy").setLevel(logging.WARNING)

app = FastAPI(
    title="HiveMind API",
    version="0.2.0",
    description="Evidence-backed causal inference API for cyber decision support.",
)


def _allowed_origins() -> list[str]:
    """Return CORS origins from env, with a local-demo-safe default."""

    configured = os.getenv("HIVEMIND_ALLOWED_ORIGINS", "")
    if configured.strip():
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    """Request body for the full agentic workflow."""

    task_description: str = Field(
        min_length=20,
        description="Natural-language incident or decision scenario.",
    )
    evidence_records: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional normalized evidence records for causal estimation.",
    )


class EstimateRequest(BaseModel):
    """Request body for deterministic evidence-backed estimation."""

    graph: dict[str, Any] = Field(
        description="Causal graph containing treatment, outcome, and confounders.",
    )
    evidence_records: list[dict[str, Any]] = Field(
        description="Normalized evidence records to compile into observations.",
    )


class NormalizeRequest(BaseModel):
    """Request body for export-to-evidence normalization endpoints."""

    records: list[dict[str, Any]] = Field(
        description="Raw exported records from the upstream system.",
    )
    source_name: str | None = Field(
        default=None,
        description="Optional concrete feed/index/export name for provenance.",
    )


@app.get("/")
def read_root():
    """Return human-readable API orientation links."""

    return {
        "message": "Welcome to the HiveMind API",
        "docs_url": "/docs",
        "health_check": "/health",
        "demo_estimate": "/demo/estimate",
        "normalizers": [
            "/normalize/sentinel",
            "/normalize/cve",
            "/normalize/incidents",
        ],
    }


@app.get("/health")
def health_check():
    """Return a minimal readiness signal for Docker and load balancers."""

    return {"status": "ok"}


@app.post("/run")
async def run_engine(request: RunRequest):
    """Execute the full agent graph and optional evidence-backed estimator."""

    logger.info("Received request to run HiveMind engine")
    try:
        result = await run_hivemind(
            request.task_description,
            evidence_records=request.evidence_records,
        )
        logger.info(
            "Successfully generated output for run_id: %s",
            result.get("run_id"),
        )
        return result
    except Exception as exc:
        logger.exception("Error executing run_hivemind")
        raise HTTPException(
            status_code=500,
            detail="HiveMind execution failed. See API logs for details.",
        ) from exc


@app.post("/estimate")
async def estimate_from_evidence(request: EstimateRequest):
    """Compile caller evidence and return a causal estimate report."""

    compilation = await asyncio.to_thread(
        compile_evidence_dataset,
        request.graph,
        request.evidence_records,
    )
    report = await asyncio.to_thread(
        estimate_causal_effect,
        request.graph,
        compilation.dataframe,
        compilation.profile,
    )
    return {
        "causal_estimate_report": report.model_dump(),
        "causal_dataset_profile": compilation.profile.model_dump(),
        "provenance": compilation.provenance,
    }


@app.post("/normalize/sentinel")
def normalize_sentinel_export(request: NormalizeRequest):
    """Normalize Microsoft Sentinel or SIEM-like export rows."""

    return {
        "evidence_records": list(normalize_sentinel_records(
            request.records,
            source_name=request.source_name or "microsoft-sentinel-export",
        ))
    }


@app.post("/normalize/cve")
def normalize_cve_export(request: NormalizeRequest):
    """Normalize NVD/CVE feed rows into evidence records."""

    return {
        "evidence_records": list(normalize_cve_records(
            request.records,
            source_name=request.source_name or "cve-feed-export",
        ))
    }


@app.post("/normalize/incidents")
def normalize_incident_export(request: NormalizeRequest):
    """Normalize incident-report export rows into evidence records."""

    return {
        "evidence_records": list(normalize_incident_reports(
            request.records,
            source_name=request.source_name or "incident-report-export",
        ))
    }


@app.get("/demo/estimate")
async def demo_estimate():
    """Run a deterministic SIEM-style evidence-backed causal estimate."""

    graph = patch_lateral_movement_graph()
    evidence = patch_lateral_movement_evidence()
    compilation = await asyncio.to_thread(compile_evidence_dataset, graph, evidence)
    report = await asyncio.to_thread(estimate_causal_effect, graph, compilation.dataframe, compilation.profile)
    return {
        "scenario": "patching reduces observed lateral movement",
        "graph": graph,
        "causal_estimate_report": report.model_dump(),
        "causal_dataset_profile": compilation.profile.model_dump(),
        "provenance_sample": compilation.provenance[:5],
    }
