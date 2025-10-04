# AI-Powered Amount Detection Service

## Problem Statement (SDE Internship Assignment)
The goal of this project was to design and implement a robust service capable of extracting, normalizing, and classifying financial amounts from unstructured medical documents (bills/receipts), handling real-world challenges like OCR errors and noisy input.

The pipeline must perform four main steps: OCR/Text Extraction, Numeric Normalization, Context Classification, and structured JSON output with provenance.

---

## 🚀 Key Features Implemented
- **Complete Pipeline:** Successfully implemented and integrated all four required steps (OCR/Text Extraction, Normalization, Classification, and Final Output).
- **Validation Guardrail:** Includes a Validation & Reconciliation layer that verifies arithmetic consistency (Paid + Due ≈ Total) and flags discrepancies in the final output.
- **Heuristic Confidence Scoring:** Calculates an overall confidence score based on the ratio of successfully classified tokens and the number of corrections required during normalization.
- **Robust Normalization:** Uses an expanded confusion map to fix common OCR digit errors (e.g., l → 1, E → 3, ; → .) to prevent them from corrupting the parsing.
- **Modular Architecture:** Logic is cleanly separated into `amount_extractor.py` (core functions) and `amount_detector_service.py` (API wrapper).

---

## 💻 Setup and Run Instructions

### Prerequisites
- Python 3.0+
- Tesseract OCR: Required for image processing.

Install Tesseract:
```bash
# macOS (Homebrew)
brew install tesseract

# Linux (Ubuntu/Debian)
sudo apt-get install tesseract-ocr
```

### Steps to Run
1. **Clone the repository:**
```bash
git clone [YOUR-REPO-URL]
cd amount_service
```

2. **Create and activate a virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate  # On Linux/macOS
venv\Scripts\activate.bat # On Windows CMD
```

3. **Install Python dependencies:**
```bash
pip install fastapi uvicorn pillow pytesseract python-multipart
```

4. **Start the API server:**
```bash
uvicorn amount_detector_service:app --reload --port 8000
```

---

## ✅ Demo and Testing

The service exposes a single POST endpoint at `http://127.0.0.1:8000/v1/amounts/extract`.

### Example 1: Plain Text Input (Validation Success)
```bash
curl -X POST http://127.0.0.1:8000/v1/amounts/extract -F "text=Total: 1500 | Paid: 1250 | Tax: 50 | Due: 250 | Discount: 10%" -F "currency_hint=INR"
```
**Output:**
```json
{
  "confidence": 0.97,
  "currency": "INR",
  "amounts": [
    {"type": "total_bill", "value": 1500.0, "source": "Total: 1500"},
    {"type": "paid", "value": 1250.0, "source": "Paid: 1250"},
    {"type": "tax", "value": 50.0, "source": "Tax: 50"},
    {"type": "due", "value": 250.0, "source": "Due: 250"},
    {"type": "discount_pct", "value": 10.0, "source": "Discount: 10%"}
  ],
  "validation_status": "validation_ok",
  "status": "ok"
}
```


### Example 2: Image Upload (OCR, Normalization, and Classification Test)
```bash
curl -X POST http://127.0.0.1:8000/v1/amounts/extract -F "file=@./receipt.jpg" -F "currency_hint=INR"
```
**Output (Based on successful testing):**
```json
{
  "confidence": 0.82,
  "currency": "INR",
  "amounts": [
    {"type": "total_bill", "value": 16.5, "source": "* Total 16.5 Cash 20;0"},
    {"type": "paid", "value": 20.0, "source": "16.5 Cash 20;0 Change 3.5"},
    {"type": "change", "value": 3.5, "source": "20;0 Change 3.5 KAER KKK"},
    {"type": "other", "value": 11223344.0, "source": "Telp. 11223344 KARE K"},
    {"type": "other", "value": 123456.0, "source": "Approval Code #123456 KERR KAKKR"}
  ],
  "validation_status": "validation_partial",
  "status": "ok"
}
```

### Example 3: Missing Input Guardrail
```bash
curl -X POST http://127.0.0.1:8000/v1/amounts/extract -F "currency_hint=INR"
```
**Expected Output:**
- **HTTP Status Code:** `400 Bad Request`
- **Response Body:**
```json
{"detail":"Either 'file' or 'text' must be provided"}
```

---

## ⏭️ Future Improvements (Extending the Solution)
- **Machine Learning (ML) Upgrade:** Replace the rule-based classifier with a transformer model (e.g., LayoutLM) trained on SROIE or CORD for higher accuracy in classification.
- **Advanced Provenance:** Integrate Tesseract's output to include bounding box coordinates for each amount, providing visual traceability.
