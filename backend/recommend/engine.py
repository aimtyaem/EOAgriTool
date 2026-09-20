"""
backend/recommend/engine.py — Rule-based recommendation and parsing engine.

Provides:
  - generate_recommendations(analysis, context) → list[dict]
  - parse_energy_bill(file_content, format) → dict
"""

from __future__ import annotations

import re
import base64
import logging
from typing import Any

logger = logging.getLogger("eoagritool.recommend")


# ────────────────────────────────────────────────────────────
# Energy Bill Parser
# ────────────────────────────────────────────────────────────

def parse_energy_bill(file_content: str, file_format: str = "text") -> dict:
    """
    Parse energy bill content into structured data.

    Parameters
    ----------
    file_content : str
        Raw text, base64-encoded PDF/image, or HTML of the bill.
    file_format : str
        One of "text", "pdf", "image", "html".

    Returns
    -------
    dict with keys: total, usage_kwh, period_start, period_end,
                    rate_per_kwh, currency, source, warnings
    """
    result: dict[str, Any] = {
        "total": None,
        "usage_kwh": None,
        "period_start": None,
        "period_end": None,
        "rate_per_kwh": None,
        "currency": "USD",
        "source": file_format,
        "warnings": [],
    }

    try:
        text = _extract_text(file_content, file_format)
    except Exception as exc:
        logger.warning("Text extraction failed: %s", exc)
        result["warnings"].append(f"Could not extract text: {exc}")
        return result

    # --- Total amount ---
    total_match = re.search(
        r"(?:total|amount due|balance|grand total)[:\s]*[$€£]?\s*([\d,]+\.?\d*)",
        text,
        re.IGNORECASE,
    )
    if total_match:
        result["total"] = float(total_match.group(1).replace(",", ""))

    # --- Usage in kWh ---
    usage_match = re.search(
        r"(?:usage|consumption|kwh used|energy used)[:\s]*([\d,]+\.?\d*)\s*kwh",
        text,
        re.IGNORECASE,
    )
    if not usage_match:
        usage_match = re.search(r"([\d,]+\.?\d*)\s*kwh", text, re.IGNORECASE)
    if usage_match:
        result["usage_kwh"] = float(usage_match.group(1).replace(",", ""))

    # --- Billing period ---
    period_match = re.search(
        r"(?:billing period|service period|for services from)[:\s]*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:to|through|-)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if period_match:
        result["period_start"] = period_match.group(1)
        result["period_end"] = period_match.group(2)

    # --- Rate per kWh ---
    if result["total"] and result["usage_kwh"] and result["usage_kwh"] > 0:
        result["rate_per_kwh"] = round(result["total"] / result["usage_kwh"], 4)

    # --- Currency detection ---
    if "€" in text or "EUR" in text.upper():
        result["currency"] = "EUR"
    elif "£" in text or "GBP" in text.upper():
        result["currency"] = "GBP"
    elif "EGP" in text.upper():
        result["currency"] = "EGP"

    if not result["total"] and not result["usage_kwh"]:
        result["warnings"].append("Could not extract total or usage from bill text")

    return result


def _extract_text(file_content: str, file_format: str) -> str:
    """Extract plain text from file_content based on format."""
    if file_format == "text":
        return file_content

    if file_format in ("pdf", "image"):
        # Decode base64
        try:
            raw = base64.b64decode(file_content, validate=True)
        except Exception:
            # Maybe it's already plain text
            return file_content

        if file_format == "pdf":
            # Minimal PDF text extraction (stub — in production use pdfminer or Azure Form Recognizer)
            try:
                return raw.decode("utf-8", errors="ignore")
            except Exception:
                return ""

        # image: would need OCR — return empty with warning
        logger.warning("OCR not implemented for image bills — returning empty text")
        return ""

    if file_format == "html":
        # Strip HTML tags
        return re.sub(r"<[^>]+>", " ", file_content)

    return file_content


# ────────────────────────────────────────────────────────────
# Recommendation Engine
# ────────────────────────────────────────────────────────────

def generate_recommendations(analysis: dict, context: dict | None = None) -> list[dict]:
    """
    Generate actionable recommendations from analysis data.

    Parameters
    ----------
    analysis : dict
        Analysis payload. Expected keys vary by domain:
          - energy: { "usage_kwh", "total_cost", "rate_per_kwh", ... }
          - water:  { "usage_m3", "irrigation_mm", "deficit_mm", ... }
          - carbon: { "footprint_kg", "offset_kg", ... }
          - soil:   { "pH", "organic_matter_pct", "texture", ... }
    context : dict, optional
        Additional context (location, sector, previous_recommendations, etc.)

    Returns
    -------
    list of recommendation dicts, each with:
      id, category, priority, title, description, action, savings_estimate
    """
    context = context or {}
    recs: list[dict] = []
    rec_id = 0

    # --- Energy recommendations ---
    usage = analysis.get("usage_kwh")
    total_cost = analysis.get("total_cost") or analysis.get("total")
    rate = analysis.get("rate_per_kwh")

    if usage and usage > 500:
        rec_id += 1
        recs.append({
            "id": f"rec_{rec_id:03d}",
            "category": "energy",
            "priority": "high" if usage > 1000 else "moderate",
            "title": "High Energy Consumption Detected",
            "description": f"Usage of {usage:,.0f} kWh exceeds the 500 kWh efficiency threshold.",
            "action": "Audit top-consuming equipment. Shift non-critical loads to off-peak hours (22:00–06:00). Consider LED lighting and variable-frequency drives.",
            "savings_estimate": f"~{usage * 0.15:,.0f} kWh/yr (15% reduction target)",
        })

    if rate and rate > 0.15:
        rec_id += 1
        recs.append({
            "id": f"rec_{rec_id:03d}",
            "category": "energy",
            "priority": "moderate",
            "title": "Above-Average Electricity Rate",
            "description": f"Rate of ${rate:.4f}/kWh exceeds the $0.15/kWh benchmark.",
            "action": "Negotiate a time-of-use plan with your utility. Evaluate on-site solar or PPA for rate hedging.",
            "savings_estimate": f"~${(rate - 0.12) * (usage or 1000):,.0f}/yr at $0.12/kWh equivalent",
        })

    # --- Water recommendations ---
    irrigation_mm = analysis.get("irrigation_mm")
    deficit_mm = analysis.get("deficit_mm")

    if irrigation_mm and irrigation_mm > 800:
        rec_id += 1
        recs.append({
            "id": f"rec_{rec_id:03d}",
            "category": "water",
            "priority": "high",
            "title": "Irrigation Volume Exceeds Efficient Threshold",
            "description": f"Annual irrigation of {irrigation_mm:.0f} mm exceeds the 800 mm water-efficient benchmark for this region.",
            "action": "Transition to deficit irrigation scheduling (80% ETc vegetative, 100% ETc reproductive). Replace flood with drip/trickle. Avoid rice in rotation.",
            "savings_estimate": f"~{irrigation_mm * 0.20:.0f} mm/yr (20% savings target)",
        })

    if deficit_mm and deficit_mm < -20:
        rec_id += 1
        recs.append({
            "id": f"rec_{rec_id:03d}",
            "category": "water",
            "priority": "critical",
            "title": "Significant Rainfall Deficit",
            "description": f"GPM rainfall anomaly of {deficit_mm:.1f} mm indicates severe moisture stress.",
            "action": "Activate emergency irrigation protocol. Prioritize high-value crops. Consider drought-tolerant varieties for next season.",
            "savings_estimate": "Crop loss prevention: 10–30% yield at risk",
        })

    # --- Soil recommendations ---
    ph = analysis.get("pH")
    om = analysis.get("organic_matter_pct")

    if ph and ph > 8.0:
        rec_id += 1
        recs.append({
            "id": f"rec_{rec_id:03d}",
            "category": "soil",
            "priority": "high",
            "title": "Alkaline Soil — Nutrient Availability Risk",
            "description": f"Soil pH {ph:.2f} exceeds 8.0. P, Fe, Zn, Mn availability significantly reduced.",
            "action": "Apply band-acidified P fertilizer (MAP + elemental S). Use Fe-EDDHA and Zn-EDTA chelates. Prioritize legume residues for organic acidification.",
            "savings_estimate": "20–40% improvement in P uptake efficiency",
        })

    if om is not None and om < 1.5:
        rec_id += 1
        recs.append({
            "id": f"rec_{rec_id:03d}",
            "category": "soil",
            "priority": "critical",
            "title": "Organic Matter Critically Low",
            "description": f"OM at {om:.2f}% is below the 1.5% minimum for sustainable soil function.",
            "action": "Incorporate legume green manure (berseem clover: 8–12 t/ha fresh biomass in 60 days). Return all crop residues. Reduce tillage. Target +0.1–0.15% OM/yr.",
            "savings_estimate": "15–25% yield improvement over 3 years as SOM recovers",
        })

    # --- Carbon recommendations ---
    footprint = analysis.get("footprint_kg") or analysis.get("carbon_footprint_kg")
    if footprint and footprint > 5000:
        rec_id += 1
        recs.append({
            "id": f"rec_{rec_id:03d}",
            "category": "carbon",
            "priority": "high",
            "title": "Carbon Footprint Exceeds Target",
            "description": f"Annual footprint of {footprint:,.0f} kg CO₂e exceeds the 5,000 kg sustainability target.",
            "action": "Switch to renewable energy (solar PPA or on-site). Optimise fertiliser application (N₂O reduction). Improve fleet efficiency. Purchase verified carbon offsets for residual.",
            "savings_estimate": f"Target: reduce to {footprint * 0.7:,.0f} kg CO₂e (30% reduction)",
        })

    # --- Crop rotation (if previous_crop given) ---
    prev_crop = (context.get("previous_crop") or analysis.get("previous_crop", "")).lower()
    n_heavy = {"wheat", "maize", "rice", "cotton", "sorghum", "barley"}
    if prev_crop in n_heavy:
        rec_id += 1
        recs.append({
            "id": f"rec_{rec_id:03d}",
            "category": "rotation",
            "priority": "high",
            "title": f"Legume Succession Required After {prev_crop.title()}",
            "description": f"{prev_crop.title()} is N-heavy. A legume successor is required to replenish soil N.",
            "action": "Plant soybean, berseem clover, fava bean, or cowpea next. Target 80–150 kg N/ha fixation. Incorporate residues for full N credit.",
            "savings_estimate": "50–70% reduction in synthetic N fertiliser cost",
        })

    if not recs:
        recs.append({
            "id": "rec_000",
            "category": "general",
            "priority": "info",
            "title": "No Critical Issues Detected",
            "description": "All monitored parameters are within acceptable ranges.",
            "action": "Continue routine monitoring and standard management practices.",
            "savings_estimate": None,
        })

    return recs