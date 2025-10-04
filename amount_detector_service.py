"""
amount_detector_service.py
===========================

This module exposes the amount extraction pipeline defined in
``amount_extractor.py`` as a RESTful API using FastAPI.  It defines a
single endpoint, ``/v1/amounts/extract``, which accepts either a
piece of text or an image file via a multipart form.  The endpoint
invokes functions from ``amount_extractor`` to perform OCR (when
available), tokenisation, normalisation and classification.  The
resulting amounts are returned in a structured JSON object.

Note that ``FastAPI`` automatically requires ``python‑multipart`` for
parsing form data.  If ``python‑multipart`` is not installed in your
environment you can still import and use the functions in
``amount_extractor.py`` directly without spinning up this web
service.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

import amount_extractor as ae


app = FastAPI(
    title="Amount Extraction Service",
    version="0.1",
    description=(
        "Extracts monetary amounts from text or images and returns them in a structured JSON format."
    ),
)


@app.post("/v1/amounts/extract")
async def extract_amounts(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    currency_hint: Optional[str] = Form(None),
    llm_mode: Optional[str] = Form("off"),
):
    """Main API endpoint for amount extraction.

    Either ``file`` or ``text`` must be provided.  When a file is
    provided the service attempts OCR, otherwise it uses the supplied
    text directly.  ``currency_hint`` is optional and echoed back in
    the response; ``llm_mode`` is reserved for future use.
    """
    if file is None and not text:
        raise HTTPException(status_code=400, detail="Either 'file' or 'text' must be provided")
    # Step 1: obtain raw text
    extracted_text = ""
    if file is not None:
        try:
            file_bytes = await file.read()
            extracted_text = ae.extract_text_from_image(file_bytes)
        except RuntimeError as e:
            return JSONResponse(status_code=422, content={"status": "ocr_unavailable", "reason": str(e)})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to process image: {e}")
    else:
        extracted_text = text or ""
     
        
    # Step 2: tokenise and normalise
    tokens,tokens_corrected, total_tokens = ae.find_numeric_tokens(extracted_text, window=2)
    if not tokens:
        return JSONResponse(status_code=422, content={"status": "no_amounts_found", "reason": "document too noisy"})
    correction_penalty = 0.25 
    normalization_confidence = 1.0 
    if total_tokens > 0:
        penalty = (tokens_corrected / total_tokens) * correction_penalty
        normalization_confidence = max(0.6, 1.0 - penalty)
    # Step 3: classification
    amounts = ae.classify_amounts(tokens)
    classified_amounts_count = len([a for a in amounts if a['type'] != 'other'])
    classification_confidence = min(0.95, classified_amounts_count / len(amounts))
    
    overall_confidence = (normalization_confidence * 0.5) + (classification_confidence * 0.5)
    validated_amounts, validation_status = ae.validate_amounts(amounts)
    response = {
        "confidence": round(overall_confidence, 2),
        "currency": currency_hint or "",
        "amounts": validated_amounts,
        "validation_status": validation_status,
        "status": "ok",
    }
    return JSONResponse(status_code=200, content=response)