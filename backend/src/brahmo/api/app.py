"""The HTTP service.

Route layout mirrors the Next.js API it replaces — ``/safety-check``,
``/compose-prompt`` — so the existing frontend can point at this with no
changes beyond a base URL.

The ordering guarantee is structural rather than documentary. ``/safety-check``
and ``/compose-prompt`` touch :mod:`brahmo.model` nowhere; only ``/consult``
does, and it computes the report and the prompt first and passes them in. A
test blocks sockets for the whole process and drives every deterministic
endpoint through, so the claim fails loudly if a model call is ever introduced
upstream of a verdict.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from brahmo.api.schemas import (
    ComposeRequest,
    ConsultRequest,
    Health,
    PatientRef,
    PatientSummary,
)
from brahmo.corpus import Corpus, CorpusError, load_default
from brahmo.model import ModelClient, ModelUnavailable, NoModel

DEFAULT_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def create_app(
    corpus: Corpus | None = None,
    model: ModelClient | None = None,
    allow_origins: tuple[str, ...] = DEFAULT_ORIGINS,
) -> FastAPI:
    """Build the service. Everything it depends on is passed in, not imported."""
    resolved_corpus = corpus if corpus is not None else load_default()
    resolved_model: ModelClient = model if model is not None else NoModel()

    app = FastAPI(
        title="BRAHMO clinical safety API",
        version="0.1.0",
        summary="Deterministic clinical decision support for Indian practice.",
        description=(
            "Dosing limits, interactions and contraindications are settled here "
            "before any language model is consulted. `/safety-check` and "
            "`/compose-prompt` never reach the network."
        ),
    )
    app.state.corpus = resolved_corpus
    app.state.model = resolved_model

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allow_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )

    @app.middleware("http")
    async def record_duration(request: Request, call_next: Callable) -> Any:
        """Server-timing on every response.

        The seam the roadmap's query telemetry hangs off: one place that already
        knows the route and the wall-clock cost, so shipping those to a
        time-series store later is a sink swap rather than a refactor.
        """
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.2f}"
        return response

    @app.exception_handler(CorpusError)
    async def corpus_error(_: Request, exc: CorpusError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    def get_corpus() -> Corpus:
        return app.state.corpus

    def get_model() -> ModelClient:
        return app.state.model

    @app.get("/health", response_model=Health, tags=["meta"])
    def health(corpus: Corpus = Depends(get_corpus)) -> Health:
        return Health(
            status="ok",
            corpus=corpus.describe(),
            model=app.state.model.name,
        )

    @app.get("/patients", tags=["patients"])
    def list_patients(
        detail: str = "summary", corpus: Corpus = Depends(get_corpus)
    ) -> list[dict[str, Any]]:
        """The seeded patients.

        ``detail=summary`` (the default) is enough to render a picker.
        ``detail=full`` returns whole records, which is what a patient panel
        needs and what saves it a request per patient to fill one in.
        """
        if detail not in ("summary", "full"):
            raise HTTPException(
                status_code=422, detail="detail must be 'summary' or 'full'"
            )
        if detail == "full":
            return [p.model_dump(by_alias=True) for p in corpus.seeded_patients]
        return [PatientSummary.of(p).model_dump() for p in corpus.seeded_patients]

    @app.get("/patients/{patient_id}", tags=["patients"])
    def get_patient(patient_id: int, corpus: Corpus = Depends(get_corpus)) -> dict[str, Any]:
        patient = corpus.patient(patient_id)
        if patient is None:
            raise HTTPException(status_code=404, detail=f"no patient {patient_id}")
        return patient.model_dump(by_alias=True)

    @app.post("/safety-check", tags=["deterministic"])
    def safety_check(body: PatientRef, corpus: Corpus = Depends(get_corpus)) -> dict[str, Any]:
        """The deterministic verdict. Reaches no network and consults no model."""
        patient = body.resolve(corpus.patient)
        return corpus.engine.run(patient).to_dict()

    @app.post("/compose-prompt", tags=["deterministic"])
    def compose_prompt(
        body: ComposeRequest, corpus: Corpus = Depends(get_corpus)
    ) -> dict[str, Any]:
        """The prompt the model *would* be given, without giving it to one."""
        patient = body.resolve(corpus.patient)
        report = corpus.engine.run(patient)
        composed = corpus.composer.compose(patient, report, body.question)
        return {"report": report.to_dict(), **composed.to_dict()}

    @app.post("/consult", tags=["model"])
    def consult(
        body: ConsultRequest,
        corpus: Corpus = Depends(get_corpus),
        model: ModelClient = Depends(get_model),
    ) -> dict[str, Any]:
        """Safety first, then the model — and the report is returned either way.

        A deployment with no model configured still gets the verdict and the
        prompts, with ``answers`` reporting why nothing was generated. The
        clinical content of this response does not depend on the model
        answering.
        """
        patient = body.resolve(corpus.patient)
        report = corpus.engine.run(patient)
        composed = corpus.composer.compose(patient, report, body.question)

        answers: dict[str, Any] = {"model": model.name}
        try:
            answers["grounded"] = model.complete(composed.grounded)
            if body.include_generic:
                answers["generic"] = model.complete(composed.generic)
        except ModelUnavailable as exc:
            answers["error"] = str(exc)

        return {
            "report": report.to_dict(),
            "meta": composed.meta.to_dict(),
            "answers": answers,
        }

    return app


app = create_app
