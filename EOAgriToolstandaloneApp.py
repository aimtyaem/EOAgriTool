#!/usr/bin/env python3
"""Standalone EUS agriculture/energy advisor.

The program is intentionally self-contained: it can install its Python
 dependencies, run outside Colab, and starts the Flask API even when an
 optional model, dataset, GPU, or Cloudflare binary is unavailable.

Examples:
    python EOAgriToolstandaloneApp.py
    python EOAgriToolstandaloneApp.py --no-install --no-vllm
    EUS_HF_TOKEN=... python EOAgriToolstandaloneApp.py --tunnel
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Installation and hardware setup (must run before third-party imports)
# ---------------------------------------------------------------------------
def _run(command: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, capture_output=True, check=check)


def detect_hardware() -> dict[str, Any]:
    result = {"type": "cpu", "name": "CPU", "vram_gb": 0.0, "count": 0, "cc": None}
    try:
        probe = _run(["nvidia-smi", "--query-gpu=name,memory.total,compute_cap",
                      "--format=csv,noheader,nounits"])
        rows = [x.strip() for x in probe.stdout.splitlines() if x.strip()]
        if rows:
            parsed = []
            for row in rows:
                parts = [x.strip() for x in row.split(",")]
                try:
                    parsed.append((parts[0], float(parts[1]) / 1024,
                                   parts[2] if len(parts) > 2 else None))
                except (IndexError, ValueError):
                    continue
            if parsed:
                gpu = max(parsed, key=lambda x: x[1])
                result.update(type="gpu", name=gpu[0], vram_gb=round(gpu[1], 1),
                              count=len(parsed), cc=gpu[2])
    except (OSError, subprocess.SubprocessError):
        pass
    return result


def install_requirements(hw: dict[str, Any], skip_vllm: bool = False) -> None:
    """Install only missing packages; do not destroy the runtime's numeric stack."""
    packages = {
        "flask": "flask>=3.0",
        "flask_cors": "flask-cors>=4.0",
        "requests": "requests>=2.31",
        "openai": "openai>=1.30",
        "numpy": "numpy>=1.24,<3",
        "joblib": "joblib>=1.3",
        "sklearn": "scikit-learn>=1.3,<2",
        "pandas": "pandas>=2.0,<3",
        "datasets": "datasets>=2.18",
        "geopy": "geopy>=2.4",
        "timezonefinder": "timezonefinder>=6.2",
        "pytz": "pytz>=2023.3",
    }
    if hw["type"] == "gpu" and not skip_vllm:
        packages["vllm"] = "vllm>=0.6"

    missing = [spec for module, spec in packages.items()
               if importlib.util.find_spec(module) is None]
    if not missing:
        print("✅ Required Python packages are already installed.")
        return
    print("📦 Installing missing packages:", ", ".join(missing))
    command = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir"] + missing
    result = _run(command)
    if result.returncode:
        print(result.stderr[-4000:])
        raise RuntimeError("Package installation failed. Run with --no-install after fixing pip.")
    print("✅ Package installation complete.")


_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--no-install", action="store_true")
_parser.add_argument("--no-vllm", action="store_true")
_parser.add_argument("--tunnel", action="store_true")
_parser.add_argument("--host", default=os.getenv("EUS_HOST", "0.0.0.0"))
_parser.add_argument("--port", type=int, default=int(os.getenv("EUS_PORT", "5000")))
_boot_args, _ = _parser.parse_known_args()
HW = detect_hardware()
print(f"🖥 Hardware: {HW['type'].upper()} | {HW['name']} | VRAM/device: {HW['vram_gb']} GB")
if not _boot_args.no_install and os.getenv("EUS_AUTO_INSTALL", "1") != "0":
    install_requirements(HW, _boot_args.no_vllm or os.getenv("EUS_DISABLE_VLLM") == "1")

# Third-party imports are deliberately after installation.
import joblib
import numpy as np
import pandas as pd
import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from openai import OpenAI
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

try:
    from datasets import load_dataset
except Exception:
    load_dataset = None
try:
    from geopy.geocoders import Nominatim
except Exception:
    Nominatim = None
try:
    from timezonefinder import TimezoneFinder
except Exception:
    TimezoneFinder = None
import pytz


# ---------------------------------------------------------------------------
# Configuration and optional services
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("EUS_DATA_DIR", str(ROOT / "eus_data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR = ROOT / "static"
MODEL_DIR = DATA_DIR / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_ID = os.getenv("EUS_MODEL_ID", "Azure99/Blossom-V7-9B")
VLLM_HOST = os.getenv("EUS_VLLM_HOST", "127.0.0.1")
VLLM_PORT = int(os.getenv("EUS_VLLM_PORT", "8000"))
MAX_LEN = int(os.getenv("EUS_MAX_LEN", "4096"))
GPU_UTIL = float(os.getenv("EUS_GPU_UTIL", "0.85"))
DISASTER_DATASET = os.getenv(
    "EUS_DISASTER_DATASET",
    "electricsheepafrica/africa-unsdg-direct-agriculture-loss-attributed-to-disasters-current-vc-dsr-aglh",
)
SCOPE_DEFAULT = "Scope 2 - Electricity Indirect"
classifier = encoder = feature_cols = None
current_scope = SCOPE_DEFAULT
vllm_proc = None


def load_disaster_data() -> pd.DataFrame:
    if load_dataset is None or os.getenv("EUS_DISABLE_DATASET") == "1":
        return pd.DataFrame()
    try:
        ds = load_dataset(DISASTER_DATASET, split="train")
        frame = ds.to_pandas()
        for col in ("year", "value"):
            if col in frame:
                frame[col] = pd.to_numeric(frame[col], errors="coerce")
        return frame.dropna(subset=["year", "value"])
    except Exception as exc:
        print(f"⚠ Disaster dataset unavailable: {exc}")
        return pd.DataFrame()


disaster_df = load_disaster_data()


def start_vllm() -> None:
    global vllm_proc
    if _boot_args.no_vllm or os.getenv("EUS_DISABLE_VLLM") == "1" or HW["type"] != "gpu":
        print("ℹ vLLM disabled (use a GPU and omit --no-vllm to enable it).")
        return
    if importlib.util.find_spec("vllm") is None:
        print("⚠ vLLM is not installed; API will run without LLM inference.")
        return
    log_path = DATA_DIR / "vllm.log"
    command = [sys.executable, "-m", "vllm.entrypoints.openai.api_server",
               "--model", MODEL_ID, "--max-model-len", str(MAX_LEN),
               "--gpu-memory-utilization", str(GPU_UTIL), "--dtype", "auto",
               "--trust-remote-code", "--host", VLLM_HOST, "--port", str(VLLM_PORT)]
    if HW.get("cc") and float(HW["cc"]) < 8:
        command.append("--enforce-eager")
    try:
        log = open(log_path, "w", encoding="utf-8")
        vllm_proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        print(f"🚀 vLLM started as PID {vllm_proc.pid}; log: {log_path}")
    except Exception as exc:
        print(f"⚠ Could not start vLLM: {exc}")


def vllm_available() -> bool:
    try:
        response = requests.get(f"http://{VLLM_HOST}:{VLLM_PORT}/v1/models", timeout=1)
        return response.ok and bool(response.json().get("data"))
    except Exception:
        return False


client = OpenAI(base_url=f"http://{VLLM_HOST}:{VLLM_PORT}/v1", api_key="not-needed")


# ---------------------------------------------------------------------------
# Data/model helpers
# ---------------------------------------------------------------------------
def loss_for(country: str, year: int):
    if disaster_df.empty or "country_iso3" not in disaster_df:
        return None, None, "Dataset not available"
    rows = disaster_df[disaster_df.country_iso3.astype(str).str.upper() == country.upper()]
    if rows.empty:
        return None, None, "No data available for this country"
    exact = rows[rows.year.astype(int) == int(year)]
    selected = exact if not exact.empty else rows[rows.year == rows.year.max()]
    used = int(selected.iloc[0].year)
    return float(selected.iloc[0].value), used, "Exact match" if not exact.empty else f"Most recent year available: {used}"


def severity(value):
    if value is None: return "unknown", "No data available"
    if value < 100: return "very_low", "Very Low Impact (< $100)"
    if value < 1000: return "low", "Low Impact ($100 - $1,000)"
    if value < 10000: return "medium", "Medium Impact ($1,000 - $10,000)"
    if value < 100000: return "high", "High Impact ($10,000 - $100,000)"
    return "very_high", "Very High Impact (> $100,000)"


def country_from_coordinates(lat, lon):
    if Nominatim is None: return None
    try:
        location = Nominatim(user_agent="eus-agri-tool/1.0").reverse(
            (float(lat), float(lon)), exactly_one=True, language="en", timeout=5)
        code = (location.raw.get("address", {}).get("country_code") if location else "")
        return {"eg": "EGY", "ke": "KEN", "ng": "NGA", "za": "ZAF", "et": "ETH", "gh": "GHA"}.get(code.lower(), code.upper()) if code else None
    except Exception:
        return None


def local_timezone(lat, lon):
    try:
        name = TimezoneFinder().timezone_at(lat=float(lat), lng=float(lon)) if TimezoneFinder else None
        return pytz.timezone(name) if name else pytz.UTC
    except Exception:
        return pytz.UTC


def train_classifier():
    global classifier, encoder, feature_cols
    if load_dataset is None: return
    try:
        frame = load_dataset("ftopal/huggingface-models-processed", split="train").to_pandas()
        numeric = frame.select_dtypes(include=[np.number]).columns.tolist()
        target = next((x for x in ("co2_eq_emissions", "co2", "emissions", "carbon") if x in frame), numeric[-1] if numeric else None)
        if not target: return
        feature_cols = [x for x in numeric if x != target][:9]
        frame = frame.dropna(subset=feature_cols + [target])
        if len(frame) < 20 or not feature_cols: return
        labels = pd.qcut(frame[target], 5, labels=["Very Low", "Low", "Medium", "High", "Very High"], duplicates="drop")
        encoder = LabelEncoder().fit(labels.astype(str))
        classifier = RandomForestClassifier(n_estimators=120, max_depth=12, random_state=42, n_jobs=-1)
        classifier.fit(frame[feature_cols], encoder.transform(labels.astype(str)))
        joblib.dump((classifier, encoder, feature_cols), MODEL_DIR / "classifier.joblib")
    except Exception as exc:
        print(f"⚠ Classifier training skipped: {exc}")


def load_classifier():
    global classifier, encoder, feature_cols
    path = MODEL_DIR / "classifier.joblib"
    try:
        classifier, encoder, feature_cols = joblib.load(path)
    except Exception:
        train_classifier()


def classify(features):
    if classifier is None:
        energy = float(features.get("energy_consumption_kwh", features.get("energy", 0)) or 0)
        label = "Very High" if energy > 1000 else "High" if energy > 500 else "Medium" if energy > 250 else "Low"
        return {"class": label, "confidence": None, "recommendations": ["Reduce peak electricity use and improve appliance efficiency."]}
    try:
        values = np.array([[float(features.get(c, 0) or 0) for c in feature_cols]])
        probs = classifier.predict_proba(values)[0]
        index = int(np.argmax(probs))
        return {"class": encoder.inverse_transform([index])[0], "confidence": round(float(probs[index]), 4),
                "class_probabilities": {encoder.inverse_transform([i])[0]: round(float(p), 4) for i, p in enumerate(probs)}}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
CORS(app)


def llm_json(system: str, user: str, tokens: int = 1024):
    if not vllm_available():
        return None
    try:
        response = client.chat.completions.create(model=MODEL_ID, messages=[
            {"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=tokens, temperature=0.3)
        text = response.choices[0].message.content or ""
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        return json.loads(text)
    except Exception:
        return None


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html") if (STATIC_DIR / "index.html").exists() else jsonify({"service": "EUS", "status": "running"})

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "llm_ready": vllm_available(), "model": MODEL_ID,
                    "scope": current_scope, "disaster_data_available": not disaster_df.empty,
                    "timestamp": datetime.now(timezone.utc).isoformat()})

@app.route("/api/scope", methods=["GET", "POST"])
def scope_route():
    global current_scope
    if request.method == "POST":
        value = (request.get_json(silent=True) or {}).get("scope")
        if not value: return jsonify({"error": "Missing scope"}), 400
        current_scope = str(value)
    return jsonify({"scope": current_scope, "success": True})

@app.post("/api/analyze-bill")
def analyze_bill():
    text = (request.get_json(silent=True) or {}).get("bill_text", "").strip()
    if not text: return jsonify({"error": "Missing bill_text"}), 400
    result = llm_json(f"Analyze an Egyptian energy bill. Scope: {current_scope}. Return JSON with analysis, reasoning, recommendations, estimated_savings_kwh, estimated_co2_reduction_kg.", text)
    return jsonify(result or {"analysis": "LLM is not running. Start with a GPU/vLLM or configure an OpenAI-compatible endpoint.", "structured": False})

@app.post("/classify_emissions")
def classify_route():
    data = request.get_json(silent=True) or {}
    return jsonify(classify(data)) if data else (jsonify({"error": "Send JSON feature values"}), 400)

@app.get("/api/disaster-loss")
def disaster_loss():
    country = request.args.get("country_iso3", "EGY").upper()
    year = request.args.get("year", datetime.now().year, type=int)
    value, used, source = loss_for(country, year)
    level, description = severity(value)
    return jsonify({"country_iso3": country, "requested_year": year, "used_year": used,
                    "loss_value_usd": value, "severity_level": level,
                    "severity_description": description, "data_source": source})

@app.post("/api/disaster-notification")
def notification():
    data = request.get_json(silent=True) or {}
    lat, lon = data.get("latitude", 30.0444), data.get("longitude", 31.2357)
    country = (data.get("country_iso3") or country_from_coordinates(lat, lon) or "EGY").upper()
    value, year, source = loss_for(country, datetime.now().year)
    level, description = severity(value)
    alert = "critical" if level in ("high", "very_high") else "warning" if level == "medium" else "info"
    return jsonify({"notification_id": f"disaster_{int(time.time())}", "alert_level": alert,
                    "title": f"Disaster status for {country}", "message": description,
                    "location": {"country_iso3": country, "latitude": lat, "longitude": lon},
                    "disaster_data": {"loss_value_usd": value, "severity_level": level, "year": year, "data_source": source},
                    "recommendations": ["Monitor weather and maintain water reserves", "Use resilient crop varieties", "Review emergency plans"]})

@app.post("/api/disaster-recommendations")
def recommendations():
    data = request.get_json(silent=True) or {}
    country = str(data.get("country_iso3", "EGY")).upper()
    value, year, _ = loss_for(country, datetime.now().year)
    level, description = severity(value)
    soil = data.get("soil_data", {})
    result = llm_json("Return JSON agricultural disaster recommendations with disaster_assessment, immediate_actions, agricultural_recommendations, soil_specific_advice, seasonal_considerations, long_term_resilience, and estimated_loss_reduction_percent.", json.dumps({"country": country, "loss": value, "severity": level, "soil": soil}), 2048)
    if result is None:
        result = {"disaster_assessment": {"severity_level": level, "confidence": 0.5, "explanation": description},
                  "immediate_actions": ["Monitor forecasts and protect water supplies"],
                  "agricultural_recommendations": ["Diversify crops and use drought-tolerant varieties"],
                  "soil_specific_advice": ["Increase organic matter and avoid over-irrigation"],
                  "long_term_resilience": ["Adopt early-warning and crop-insurance plans"]}
    result["metadata"] = {"country_iso3": country, "disaster_loss_usd": value, "disaster_year": year, "soil_data": soil}
    return jsonify(result)

@app.post("/api/yield-prediction")
def yield_prediction():
    data = request.get_json(silent=True) or {}
    country, crop = str(data.get("country_iso3", "EGY")).upper(), str(data.get("crop_type", "wheat")).lower()
    date = data.get("planting_date", datetime.now().strftime("%Y-%m-%d"))
    try: month = datetime.strptime(date, "%Y-%m-%d").month
    except ValueError: return jsonify({"error": "planting_date must be YYYY-MM-DD"}), 400
    value, year, _ = loss_for(country, datetime.now().year)
    level, description = severity(value)
    base = {"wheat": 3000, "corn": 4000, "rice": 5000, "cotton": 1500, "sugarcane": 7000}.get(crop, 3000)
    risk = {"very_low": 1, "low": .95, "medium": .85, "high": .7, "very_high": .5, "unknown": .9}[level]
    soil = data.get("soil_data", {}); ph = float(soil.get("ph", 7)); organic = max(0, float(soil.get("organic_matter", 2.5)))
    soil_factor = 1.0 if 6 <= ph <= 7.5 else max(.8, .8 + .2 * (1 - abs(ph - 6.75) / 2.75))
    seasonal = 1.1 if (crop == "wheat" and month in (10, 11)) or (crop == "corn" and month in (4, 5)) else .9 if (crop == "wheat" and month in (12, 1, 2)) or (crop == "corn" and month in (6, 7)) else 1.0
    final = base * risk * soil_factor * (.7 + .3 * min(organic / 5, 1)) * seasonal
    return jsonify({"country_iso3": country, "crop_type": crop, "planting_date": date, "base_yield_kg_ha": base,
                    "soil_adjusted_yield_kg_ha": round(final, 2), "disaster_risk": {"severity_level": level, "severity_description": description, "loss_value_usd": value, "adjustment_factor": risk}, "timestamp": datetime.now(timezone.utc).isoformat()})

@app.get("/api/routes")
def routes():
    return jsonify([{"url": str(r), "endpoint": r.endpoint, "methods": sorted(r.methods - {"HEAD", "OPTIONS"})} for r in app.url_map.iter_rules()])


def launch_tunnel(port: int):
    """Use cloudflared only when explicitly requested; it is never required."""
    try:
        proc = subprocess.Popen(["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except FileNotFoundError:
        print("⚠ cloudflared is not installed; continuing without a tunnel.")
        return
    for _ in range(120):
        line = proc.stdout.readline() if proc.stdout else ""
        match = re.search(r"https://[\w-]+\.trycloudflare\.com", line)
        if match:
            print(f"🌍 Public URL: {match.group(0)}")
            return
    print("⚠ Tunnel started but its public URL was not detected.")


def main():
    global _boot_args
    _boot_args = _parser.parse_args()
    load_classifier()
    start_vllm()
    if _boot_args.tunnel:
        threading.Thread(target=launch_tunnel, args=(_boot_args.port,), daemon=True).start()
    print(f"✅ EUS listening on http://{_boot_args.host}:{_boot_args.port}")
    app.run(host=_boot_args.host, port=_boot_args.port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
