
#!/usr/bin/env python3
"""
# @title Enhanced Multimodal Egyptian Energy Advisor (EUS) — Standalone Colab Program
Flask + vLLM + Cloudflare Tunnel + Emissions Classifier + Disaster Notifications

NEW: Real-time disaster alerts using Africa UN SDG dataset + location-aware recommendations
"""

# ============================================================
# A. IMPORTS
# ============================================================
import os, sys, re, json, time, signal, threading, subprocess, textwrap
import requests, httpx, joblib, numpy as np, pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI
from datasets import load_dataset
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.preprocessing import LabelEncoder
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from timezonefinder import TimezoneFinder
import pytz
import warnings
warnings.filterwarnings("ignore")

# ============================================================
# B. CONFIGURATION
# ============================================================
MODEL_ID   = os.environ.get("EUS_MODEL_ID",   "Azure99/Blossom-V7-9B")
MAX_LEN    = int(os.environ.get("EUS_MAX_LEN",  "4096"))
GPU_UTIL   = float(os.environ.get("EUS_GPU_UTIL", "0.85"))

VLLM_PORT      = 8000
VLLM_HOST      = "localhost"
FLASK_PORT     = 5000
VLLM_TIMEOUT   = 900
VLLM_POLL_INTERVAL = 10

SCOPE_DEFAULT  = "Scope 2 - Electricity Indirect"

MODEL_DIR      = Path("/content/eus_models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)
CLASSIFIER_PATH = MODEL_DIR / "emissions_classifier.joblib"
ENCODER_PATH    = MODEL_DIR / "emissions_encoder.joblib"

# ── Disaster Dataset Configuration ──────────────────────────
DISASTER_DATASET = "electricsheepafrica/africa-unsdg-direct-agriculture-loss-attributed-to-disasters-current-vc-dsr-aglh"
DISASTER_THRESHOLD_LOW = 100      # Current USD
DISASTER_THRESHOLD_MEDIUM = 1000  # Current USD
# Loss categories: Very Low < 100, Low 100-1000, Medium 1000-10000, High 10000-100000, Very High > 100000

# ============================================================
# C. AUTHENTICATE WITH HUGINGFACE
# ============================================================
from google.colab import userdata

try:
    hf_token = userdata.get("HF_TOKEN")
    os.environ["HF_TOKEN"] = hf_token
    from huggingface_hub import login
    login(token=hf_token)
    print("✅ HuggingFace login successful.")
except Exception as e:
    print(f"❌ HF_TOKEN error: {e}")
    print("   Add HF_TOKEN to Colab Secrets (🔑 key icon in left sidebar).")
    sys.exit(1)

# ============================================================
# D. LAUNCH vLLM SERVER
# ============================================================
print(f"\n🚀 Launching vLLM with {MODEL_ID} …")

# Kill any existing vLLM
subprocess.run(["pkill", "-f", "vllm"], capture_output=True)
time.sleep(2)

vllm_cmd = [
    sys.executable, "-m", "vllm.entrypoints.openai.api_server",
    "--model",             MODEL_ID,
    "--max-model-len",     str(MAX_LEN),
    "--gpu-utilization",   str(GPU_UTIL),
    "--dtype",             "half",
    "--enforce-eager",
    "--trust-remote-code",
    "--host",              "0.0.0.0",
    "--port",              str(VLLM_PORT),
]

vllm_log = open("/content/vllm.log", "w")
vllm_proc = subprocess.Popen(
    vllm_cmd,
    stdout=vllm_log, stderr=subprocess.STDOUT,
    preexec_fn=os.setsid
)
print(f"🚀 vLLM PID={vllm_proc.pid}  (log → /content/vllm.log)")

# ── WAIT FOR vLLM READINESS ────────────────────────────────
def wait_for_vllm(host=VLLM_HOST, port=VLLM_PORT,
                   timeout=VLLM_TIMEOUT, interval=VLLM_POLL_INTERVAL):
    """Poll /v1/models until vLLM is accepting requests."""
    url = f"http://{host}:{port}/v1/models"
    start = time.time()
    while time.time() - start < timeout:
        if vllm_proc.poll() is not None:
            print(f"❌ vLLM exited with code {vllm_proc.returncode}")
            print("   Last 40 lines of log:")
            subprocess.run(["tail", "-40", "/content/vllm.log"])
            return False
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200 and r.json().get("data"):
                elapsed = time.time() - start
                print(f"✅ vLLM ready after {elapsed:.0f}s — models: "
                      f"{[m['id'] for m in r.json()['data']]}")
                return True
        except (requests.ConnectionError, requests.Timeout, Exception):
            pass
        elapsed = int(time.time() - start)
        print(f"⏳ Waiting for vLLM … {elapsed}s/{timeout}s", end="\r")
        time.sleep(interval)
    print(f"\n❌ vLLM did NOT become ready within {timeout}s.")
    return False

if not wait_for_vllm():
    raise RuntimeError("vLLM server failed to start. Check /content/vllm.log")

# ============================================================
# E. OPENAI CLIENT
# ============================================================
oai_client = OpenAI(
    base_url=f"http://{VLLM_HOST}:{VLLM_PORT}/v1",
    api_key="not-needed"
)
vllm_model_id = MODEL_ID

# ============================================================
# F. LOAD DISASTER DATASET
# ============================================================
print("\n🌍 Loading Africa UN SDG Disaster Dataset …")
try:
    disaster_dataset = load_dataset(DISASTER_DATASET)
    disaster_df = disaster_dataset['train'].to_pandas()

    # Clean and prepare data
    disaster_df['year'] = disaster_df['year'].astype(int)
    disaster_df['value'] = pd.to_numeric(disaster_df['value'], errors='coerce')

    print(f"✅ Disaster dataset loaded: {len(disaster_df)} records")
    print(f"   Countries: {disaster_df['country_name'].nunique()}")
    print(f"   Years: {disaster_df['year'].min()} - {disaster_df['year'].max()}")
    print(f"   Sample data (Egypt):")
    egypt_data = disaster_df[disaster_df['country_iso3'] == 'EGY'].tail(5)
    print(egypt_data[['year', 'value', 'country_name']].to_string(index=False))

except Exception as e:
    print(f"❌ Error loading disaster dataset: {e}")
    disaster_df = pd.DataFrame()  # Empty fallback

# ── Disaster Data Helper Functions ──────────────────────────
def get_disaster_loss(country_iso3, year):
    """Get agriculture loss for country and year, with fallback to most recent year."""
    if disaster_df.empty:
        return None, None, "Dataset not available"

    # Try exact year
    exact_match = disaster_df[
        (disaster_df['country_iso3'] == country_iso3) &
        (disaster_df['year'] == year)
    ]

    if not exact_match.empty:
        loss = exact_match.iloc[0]['value']
        return loss, year, "Exact match"

    # Fallback to most recent year for country
    country_data = disaster_df[disaster_df['country_iso3'] == country_iso3]
    if not country_data.empty:
        max_year = country_data['year'].max()
        recent_match = country_data[country_data['year'] == max_year]
        if not recent_match.empty:
            loss = recent_match.iloc[0]['value']
            return loss, max_year, f"Most recent year available: {max_year}"

    return None, None, "No data available for this country"

def classify_disaster_severity(loss_value):
    """Classify disaster severity based on agriculture loss value."""
    if loss_value is None:
        return "unknown", "No data available"

    if loss_value < DISASTER_THRESHOLD_LOW:
        return "very_low", f"Very Low Impact (< ${DISASTER_THRESHOLD_LOW:,})"
    elif loss_value < DISASTER_THRESHOLD_MEDIUM:
        return "low", f"Low Impact (${DISASTER_THRESHOLD_LOW:,} - ${DISASTER_THRESHOLD_MEDIUM:,})"
    elif loss_value < 10000:
        return "medium", f"Medium Impact (${DISASTER_THRESHOLD_MEDIUM:,} - $10,000)"
    elif loss_value < 100000:
        return "high", f"High Impact ($10,000 - $100,000)"
    else:
        return "very_high", f"Very High Impact (> $100,000)"

def get_country_from_coordinates(lat, lon):
    """Get country ISO3 code from coordinates using reverse geocoding."""
    try:
        geolocator = Nominatim(user_agent="eus_disaster_advisor")
        location = geolocator.reverse(f"{lat}, {lon}", exactly_one=True, language='en')

        if location and location.raw.get('address', {}).get('country_code'):
            country_code = location.raw['address']['country_code'].upper()
            # Convert to ISO3 if needed (simplified for demo)
            iso3_mapping = {
                'EG': 'EGY', 'KE': 'KEN', 'NG': 'NGA', 'ZA': 'ZAF',
                'ET': 'ETH', 'TZ': 'TZA', 'GH': 'GHA', 'CM': 'CMR',
                'SN': 'SEN', 'MZ': 'MOZ', 'UG': 'UGA', 'MW': 'MWI',
                'ZM': 'ZMB', 'RW': 'RWA', 'BI': 'BDI', 'BJ': 'BEN',
                'BF': 'BFA', 'CF': 'CAF', 'TD': 'TCD', 'CG': 'COG',
                'CI': 'CIV', 'CD': 'COD', 'DJ': 'DJI', 'GQ': 'GNQ',
                'ER': 'ERI', 'GA': 'GAB', 'GM': 'GMB', 'GN': 'GIN',
                'GW': 'GNB', 'LS': 'LSO', 'LR': 'LBR', 'LY': 'LBY',
                'MG': 'MDG', 'ML': 'MLI', 'MR': 'MRT', 'NA': 'NAM',
                'NE': 'NER', 'SL': 'SLE', 'SO': 'SOM', 'SS': 'SSD',
                'SZ': 'SWZ', 'TG': 'TGO', 'TN': 'TUN', 'VU': 'VUT',
                'ZM': 'ZMB', 'ZW': 'ZWE'
            }
            return iso3_mapping.get(country_code, country_code)
        return None
    except (GeocoderTimedOut, GeocoderServiceError, Exception) as e:
        print(f"Geocoding error: {e}")
        return None

def get_local_timezone(lat, lon):
    """Get timezone from coordinates."""
    try:
        tf = TimezoneFinder()
        timezone_str = tf.timezone_at(lat=lat, lng=lon)
        if timezone_str:
            return pytz.timezone(timezone_str)
        return pytz.UTC
    except Exception as e:
        print(f"Timezone error: {e}")
        return pytz.UTC

# ============================================================
# G. EMISSIONS CLASSIFIER (Original)
# ============================================================
def train_emissions_classifier():
    """Load HF dataset → engineer features → train RandomForest → save."""
    print("\n📥 Loading ftopal/huggingface-models-processed …")
    ds = load_dataset("ftopal/huggingface-models-processed", split="train")
    df = ds.to_pandas()

    # Feature engineering
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    target_col = None
    for candidate in ["co2_eq_emissions", "co2", "emissions", "carbon"]:
        if candidate in df.columns:
            target_col = candidate
            break
    if target_col is None and numeric_cols:
        target_col = numeric_cols[-1]

    feature_cols = [c for c in numeric_cols if c != target_col][:9]
    df_clean = df.dropna(subset=feature_cols + [target_col]).copy()

    # Assign emission class
    q = df_clean[target_col].quantile([0.2, 0.4, 0.6, 0.8])
    def classify(val):
        if   val <= q[0.2]: return "Very Low"
        elif val <= q[0.4]: return "Low"
        elif val <= q[0.6]: return "Medium"
        elif val <= q[0.8]: return "High"
        else:               return "Very High"
    df_clean["emission_class"] = df_clean[target_col].apply(classify)

    # Train/test split
    le = LabelEncoder()
    y = le.fit_transform(df_clean["emission_class"])
    X = df_clean[feature_cols].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=200, max_depth=12, random_state=42, n_jobs=-1
    )
    print("🏋 Training RandomForest …")
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    print("📊 Classification report:")
    print(classification_report(y_test, y_pred, target_names=le.classes_))

    joblib.dump(clf, CLASSIFIER_PATH)
    joblib.dump(le,  ENCODER_PATH)
    joblib.dump(feature_cols, MODEL_DIR / "feature_cols.joblib")
    print(f"✓ Model saved → {CLASSIFIER_PATH}")

    return clf, le, feature_cols, target_col

def load_or_train_classifier():
    """Load from disk if available, otherwise train."""
    if CLASSIFIER_PATH.exists() and ENCODER_PATH.exists():
        clf         = joblib.load(CLASSIFIER_PATH)
        le          = joblib.load(ENCODER_PATH)
        feature_cols = joblib.load(MODEL_DIR / "feature_cols.joblib")
        target_col  = "co2_eq_emissions"
        print("✓ Loaded existing emissions classifier from disk.")
        return clf, le, feature_cols, target_col
    return train_emissions_classifier()

clf, le, feature_cols, target_col = load_or_train_classifier()

def classify_emissions(features_dict):
    """Run inference on the trained classifier + generate recommendations."""
    try:
        X = np.array([[features_dict.get(c, 0) for c in feature_cols]])
        probs = clf.predict_proba(X)[0]
        pred_idx = np.argmax(probs)
        pred_class = le.inverse_transform([pred_idx])[0]
        confidence = float(probs[pred_idx])
        class_probs = {le.inverse_transform([i])[0]: round(float(p), 4)
                       for i, p in enumerate(probs)}
    except Exception as e:
        return {"error": str(e)}

    # Recommendation engine
    recs = []
    co2 = features_dict.get("co2_eq_emissions", 0)
    energy = features_dict.get("energy_consumption_kwh", features_dict.get("energy", 0))

    if pred_class in ("High", "Very High"):
        recs.append({"level": "high",  "text": "High Energy Consumption Detected"})
    elif pred_class == "Medium":
        recs.append({"level": "moderate", "text": "Moderate Energy Consumption Detected"})

    if energy > 500:
        recs.append({"level": "moderate", "text": "Above-Average Electricity Rate"})

    recs.append({"level": "high", "text": "Legume Succession Required After Wheat"})

    if pred_class == "Medium":
        recs.append({"level": "moderate", "text": "Medium Training Emissions"})

    return {
        "class":           pred_class,
        "confidence":      round(confidence, 4),
        "class_probabilities": class_probs,
        "recommendations": recs,
        "co2_kg":          round(float(co2), 3) if co2 else None,
        "energy_kwh":      round(float(energy), 3) if energy else None,
    }

# ============================================================
# H. FLASK APPLICATION — ALL ROUTES (Enhanced with Disaster)
# ============================================================
app = Flask(__name__, static_folder="/content", static_url_path="/static")
CORS(app)

# ── Shared state ────────────────────────────────────────────
current_scope = SCOPE_DEFAULT

SYSTEM_PROMPT_TEMPLATE = textwrap.dedent("""\
    You are the Eco-Urban-Space (EUS) Egyptian Energy Advisor.
    You analyze energy bills and provide actionable recommendations
    for reducing CO₂ emissions in the Egyptian context.

    Current analysis scope: {scope}

    Always respond in this JSON format:
    {{
      "analysis": "<detailed analysis text>",
      "reasoning": "<step-by-step reasoning>",
      "recommendations": ["<rec 1>", "<rec 2>", ...],
      "estimated_savings_kwh": <number>,
      "estimated_co2_reduction_kg": <number>
    }}
""")

DISASTER_SYSTEM_PROMPT_TEMPLATE = textwrap.dedent("""\
    You are the Eco-Urban-Space (EUS) Egyptian Energy Advisor, now enhanced with disaster risk reduction capabilities.

    You are provided with:
    1. Current location data (country, coordinates, timezone)
    2. Current date-time in the user's timezone
    3. Direct agriculture loss attributed to disasters for the user's country and year
    4. Available soil data (if provided)

    Your task is to:
    1. Assess the disaster risk level based on the agriculture loss data
    2. Provide specific, actionable recommendations for disaster resilience and agricultural adaptation
    3. Consider the current season and local climate patterns
    4. Integrate soil data for tailored agricultural advice
    5. Consider both immediate disaster preparedness and long-term resilience strategies

    Location: {country_name} ({country_iso3})
    Coordinates: {latitude}, {longitude}
    Timezone: {timezone}
    Current Date-Time: {current_datetime}
    Agriculture Loss: ${loss_value:,.2f} USD ({loss_category})
    Soil Data: {soil_data}

    Always respond in this JSON format:
    {{
      "disaster_assessment": {{
        "severity_level": "<very_low/low/medium/high/very_high>",
        "confidence": <0.0-1.0>,
        "explanation": "<why this severity level>"
      }},
      "immediate_actions": ["<action 1>", "<action 2>", ...],
      "agricultural_recommendations": ["<rec 1>", "<rec 2>", ...],
      "soil_specific_advice": ["<advice 1>", "<advice 2>", ...],
      "seasonal_considerations": ["<consideration 1>", ...],
      "long_term_resilience": ["<strategy 1>", ...],
      "estimated_loss_reduction_percent": <number>
    }}
""")

# ── Dashboard route ─────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("/content", "index.html")

# ── Health check ────────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    vllm_ok = False
    models_list = []
    error_msg = None
    try:
        r = requests.get(f"http://{VLLM_HOST}:{VLLM_PORT}/v1/models", timeout=5)
        if r.status_code == 200:
            data = r.json().get("data", [])
            models_list = [m["id"] for m in data]
            vllm_ok = len(models_list) > 0
    except Exception as e:
        error_msg = str(e)

    return jsonify({
        "ok":               vllm_ok,
        "backend":          "blossom-local",
        "model":            MODEL_ID,
        "base_url":         f"http://{VLLM_HOST}:{VLLM_PORT}/v1",
        "available_models": models_list,
        "scope":            current_scope,
        "server_error":     error_msg,
        "disaster_data_available": not disaster_df.empty,
        "timestamp":        datetime.now(timezone.utc).isoformat(),
    })

# ── Scope management ────────────────────────────────────────
@app.route("/api/scope", methods=["GET", "POST"])
def scope_route():
    global current_scope
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        new_scope = data.get("scope")
        if new_scope:
            current_scope = new_scope
            return jsonify({"scope": current_scope, "success": True})
        return jsonify({"error": "Missing 'scope' in JSON body"}), 400
    return jsonify({"scope": current_scope})

# ── Analyze bill (LLM inference) ────────────────────────────
@app.route("/api/analyze-bill", methods=["POST"])
def analyze_bill():
    data = request.get_json(silent=True) or {}
    bill_text = data.get("bill_text", "")
    if not bill_text:
        return jsonify({"error": "Missing 'bill_text'"}), 400

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(scope=current_scope)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = oai_client.chat.completions.create(
                model=vllm_model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": f"Analyze this energy bill:\n{bill_text}"},
                ],
                max_tokens=1024,
                temperature=0.3,
            )
            content = resp.choices[0].message.content
            try:
                parsed = json.loads(content)
                return jsonify(parsed)
            except json.JSONDecodeError:
                return jsonify({
                    "analysis": content,
                    "reasoning": None,
                    "structured": False,
                })
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return jsonify({
                "error": f"Inference error after {max_retries} attempts: {e}",
                "reasoning_present": False,
            }), 502

# ── Emissions classification ────────────────────────────────
@app.route("/classify_emissions", methods=["POST"])
def classify_emissions_route():
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "Send JSON with feature values"}), 400
    result = classify_emissions(data)
    return jsonify(result)

# ── NEW: Disaster Loss Endpoint ─────────────────────────────
@app.route("/api/disaster-loss", methods=["GET"])
def disaster_loss():
    """Get agriculture loss for a country and year."""
    country_iso3 = request.args.get("country_iso3", "EGY").upper()
    year = request.args.get("year", datetime.now().year, type=int)

    loss_value, used_year, data_source = get_disaster_loss(country_iso3, year)
    severity, severity_desc = classify_disaster_severity(loss_value)

    # Get country name from dataset
    country_name = country_iso3
    if not disaster_df.empty:
        country_row = disaster_df[disaster_df['country_iso3'] == country_iso3]
        if not country_row.empty:
            country_name = country_row.iloc[0]['country_name']

    return jsonify({
        "country_iso3": country_iso3,
        "country_name": country_name,
        "requested_year": year,
        "used_year": used_year,
        "loss_value_usd": loss_value,
        "severity_level": severity,
        "severity_description": severity_desc,
        "data_source": data_source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

# ── NEW: Disaster Notification Endpoint ─────────────────────
@app.route("/api/disaster-notification", methods=["POST"])
def disaster_notification():
    """Generate disaster notification based on user location and conditions."""
    data = request.get_json(silent=True) or {}

    # Get location from request or use defaults
    latitude = data.get("latitude", 30.0444)  # Cairo coordinates
    longitude = data.get("longitude", 31.2357)
    country_iso3 = data.get("country_iso3")

    # Get country from coordinates if not provided
    if not country_iso3:
        country_iso3 = get_country_from_coordinates(latitude, longitude)
        if not country_iso3:
            country_iso3 = "EGY"  # Default to Egypt

    # Get current date-time in user's timezone
    user_timezone = get_local_timezone(latitude, longitude)
    current_datetime = datetime.now(user_timezone)

    # Get disaster loss for current year
    loss_value, used_year, data_source = get_disaster_loss(country_iso3, current_datetime.year)
    severity, severity_desc = classify_disaster_severity(loss_value)

    # Build notification based on severity
    notification = {
        "notification_id": f"disaster_{int(time.time())}",
        "timestamp": current_datetime.isoformat(),
        "location": {
            "country_iso3": country_iso3,
            "country_name": "",
            "latitude": latitude,
            "longitude": longitude,
            "timezone": str(user_timezone)
        },
        "disaster_data": {
            "loss_value_usd": loss_value,
            "severity_level": severity,
            "severity_description": severity_desc,
            "year": used_year,
            "data_source": data_source
        },
        "alert_level": "info",
        "title": "",
        "message": "",
        "recommendations": []
    }

    # Get country name
    if not disaster_df.empty:
        country_row = disaster_df[disaster_df['country_iso3'] == country_iso3]
        if not country_row.empty:
            notification["location"]["country_name"] = country_row.iloc[0]['country_name']

    # Set alert level and message based on severity
    if severity in ("high", "very_high"):
        notification["alert_level"] = "critical"
        notification["title"] = f"🚨 Critical Disaster Alert for {notification['location']['country_name']}"
        notification["message"] = (
            f"High agriculture loss detected: ${loss_value:,.2f} USD in {used_year}. "
            f"Immediate action required for disaster resilience."
        )
        notification["recommendations"] = [
            "Activate emergency irrigation systems",
            "Implement crop insurance programs",
            "Deploy drought-resistant seed varieties",
            "Establish early warning systems",
            "Prepare contingency harvesting schedules"
        ]
    elif severity == "medium":
        notification["alert_level"] = "warning"
        notification["title"] = f"⚠️ Disaster Warning for {notification['location']['country_name']}"
        notification["message"] = (
            f"Moderate agriculture loss: ${loss_value:,.2f} USD in {used_year}. "
            f"Precautionary measures recommended."
        )
        notification["recommendations"] = [
            "Review disaster preparedness plans",
            "Stock emergency agricultural supplies",
            "Monitor weather forecasts closely",
            "Consider alternative crop rotation"
        ]
    elif severity in ("low", "very_low"):
        notification["alert_level"] = "info"
        notification["title"] = f"✅ Low Disaster Risk for {notification['location']['country_name']}"
        notification["message"] = (
            f"Agriculture loss is minimal: ${loss_value:,.2f} USD in {used_year}. "
            f"Standard precautions sufficient."
        )
        notification["recommendations"] = [
            "Maintain regular monitoring",
            "Continue standard agricultural practices",
            "Document current conditions for baseline"
        ]
    else:  # unknown
        notification["alert_level"] = "info"
        notification["title"] = f"ℹ️ No Disaster Data Available for {notification['location']['country_name']}"
        notification["message"] = "No historical disaster data available for this location."

    return jsonify(notification)

# ── NEW: Disaster-Aware Agricultural Recommendations ────────
@app.route("/api/disaster-recommendations", methods=["POST"])
def disaster_recommendations():
    """Generate LLM-powered disaster-aware agricultural recommendations."""
    data = request.get_json(silent=True) or {}

    # Extract location data
    latitude = data.get("latitude", 30.0444)
    longitude = data.get("longitude", 31.2357)
    country_iso3 = data.get("country_iso3")
    country_name = data.get("country_name", "")

    # Get country from coordinates if not provided
    if not country_iso3:
        country_iso3 = get_country_from_coordinates(latitude, longitude)
        if not country_iso3:
            country_iso3 = "EGY"

    # Get current date-time in user's timezone
    user_timezone = get_local_timezone(latitude, longitude)
    current_datetime = datetime.now(user_timezone)

    # Get disaster loss for current year
    loss_value, used_year, data_source = get_disaster_loss(country_iso3, current_datetime.year)
    severity, severity_desc = classify_disaster_severity(loss_value)

    # Get soil data
    soil_data = data.get("soil_data", {
        "ph": 7.0,
        "organic_matter": 2.5,
        "nitrogen": 25,
        "phosphorus": 15,
        "potassium": 20,
        "texture": "loam",
        "drainage": "good"
    })

    # Get country name from dataset if not provided
    if not country_name and not disaster_df.empty:
        country_row = disaster_df[disaster_df['country_iso3'] == country_iso3]
        if not country_row.empty:
            country_name = country_row.iloc[0]['country_name']

    # Prepare system prompt
    system_prompt = DISASTER_SYSTEM_PROMPT_TEMPLATE.format(
        country_name=country_name,
        country_iso3=country_iso3,
        latitude=latitude,
        longitude=longitude,
        timezone=str(user_timezone),
        current_datetime=current_datetime.strftime("%Y-%m-%d %H:%M:%S %Z"),
        loss_value=loss_value if loss_value else 0,
        loss_category=severity_desc,
        soil_data=json.dumps(soil_data, indent=2)
    )

    # User message with specific context
    user_message = textwrap.dedent(f"""\
        Based on the current conditions in {country_name}:

        1. Current season: {current_datetime.strftime('%B')} (month {current_datetime.month})
        2. Agriculture disaster loss: ${loss_value:,.2f} USD in {used_year}
        3. Soil pH: {soil_data.get('ph', 'N/A')}
        4. Primary crop: Wheat (typical for this region)

        Please provide specific recommendations for:
        - Disaster preparedness for the current season
        - Crop management considering soil conditions
        - Long-term resilience strategies
    """)

    # Call LLM with retry logic
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = oai_client.chat.completions.create(
                model=vllm_model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
                max_tokens=2048,  # Longer response for detailed recommendations
                temperature=0.4,  # Slightly higher for more creative recommendations
            )
            content = resp.choices[0].message.content

            # Try to parse as JSON
            try:
                parsed = json.loads(content)
                # Add metadata
                parsed["metadata"] = {
                    "country_iso3": country_iso3,
                    "country_name": country_name,
                    "latitude": latitude,
                    "longitude": longitude,
                    "timezone": str(user_timezone),
                    "current_datetime": current_datetime.isoformat(),
                    "disaster_loss_usd": loss_value,
                    "disaster_year": used_year,
                    "severity_level": severity,
                    "soil_data": soil_data
                }
                return jsonify(parsed)
            except json.JSONDecodeError:
                # Fallback if LLM doesn't return valid JSON
                return jsonify({
                    "disaster_assessment": {
                        "severity_level": severity,
                        "confidence": 0.8,
                        "explanation": f"Based on ${loss_value:,.2f} USD agriculture loss in {used_year}"
                    },
                    "llm_response": content,
                    "metadata": {
                        "country_iso3": country_iso3,
                        "country_name": country_name,
                        "current_datetime": current_datetime.isoformat(),
                        "disaster_loss_usd": loss_value,
                        "severity_level": severity
                    }
                })
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return jsonify({
                "error": f"Failed to generate recommendations after {max_retries} attempts: {e}",
                "fallback_recommendations": [
                    "Monitor weather conditions regularly",
                    "Maintain soil health through organic amendments",
                    "Diversify crop varieties",
                    "Implement water conservation measures",
                    "Prepare emergency irrigation systems"
                ]
            }), 502

# ── NEW: Yield Crop Prediction with Disaster Context ────────
@app.route("/api/yield-prediction", methods=["POST"])
def yield_prediction():
    """Predict crop yield considering disaster risk and soil data."""
    data = request.get_json(silent=True) or {}

    # Extract input data
    country_iso3 = data.get("country_iso3", "EGY").upper()
    crop_type = data.get("crop_type", "wheat").lower()
    planting_date = data.get("planting_date", datetime.now().strftime("%Y-%m-%d"))
    soil_data = data.get("soil_data", {})

    # Get disaster context
    loss_value, used_year, data_source = get_disaster_loss(country_iso3, datetime.now().year)
    severity, severity_desc = classify_disaster_severity(loss_value)

    # Base yield estimates (kg/hectare) - simplified model
    base_yields = {
        "wheat": 3000,
        "corn": 4000,
        "rice": 5000,
        "cotton": 1500,
        "sugarcane": 7000
    }

    base_yield = base_yields.get(crop_type, 3000)

    # Adjust for disaster risk (simplified)
    disaster_factor = {
        "very_low": 1.0,
        "low": 0.95,
        "medium": 0.85,
        "high": 0.7,
        "very_high": 0.5,
        "unknown": 0.9
    }

    adjusted_yield = base_yield * disaster_factor.get(severity, 0.9)

    # Soil quality factor (simplified)
    soil_ph = soil_data.get("ph", 7.0)
    organic_matter = soil_data.get("organic_matter", 2.5)

    # Optimal pH range for most crops: 6.0-7.5
    if 6.0 <= soil_ph <= 7.5:
        soil_factor = 1.0
    else:
        soil_factor = 0.8 + 0.2 * (1 - abs(soil_ph - 6.75) / 2.75)

    # Organic matter factor (higher is better, up to 5%)
    organic_factor = min(organic_matter / 5.0, 1.0) * 0.3 + 0.7

    final_yield = adjusted_yield * soil_factor * organic_factor

    # Seasonal adjustment (Northern Hemisphere)
    planting_month = datetime.strptime(planting_date, "%Y-%m-%d").month
    seasonal_factor = 1.0
    if crop_type == "wheat":
        # Optimal planting: October-November for winter wheat
        if planting_month in [10, 11]:
            seasonal_factor = 1.1
        elif planting_month in [12, 1, 2]:
            seasonal_factor = 0.9
    elif crop_type == "corn":
        # Optimal planting: April-May
        if planting_month in [4, 5]:
            seasonal_factor = 1.1
        elif planting_month in [6, 7]:
            seasonal_factor = 0.9

    final_yield *= seasonal_factor

    return jsonify({
        "country_iso3": country_iso3,
        "crop_type": crop_type,
        "planting_date": planting_date,
        "base_yield_kg_ha": base_yield,
        "disaster_adjusted_yield_kg_ha": adjusted_yield,
        "soil_adjusted_yield_kg_ha": final_yield,
        "disaster_risk": {
            "severity_level": severity,
            "severity_description": severity_desc,
            "loss_value_usd": loss_value,
            "adjustment_factor": disaster_factor.get(severity, 0.9)
        },
        "soil_quality": {
            "ph": soil_ph,
            "organic_matter_percent": organic_matter,
            "soil_factor": soil_factor,
            "organic_factor": organic_factor
        },
        "seasonal_factor": seasonal_factor,
        "recommendations": [
            f"Expected yield: {final_yield:,.0f} kg/hectare",
            f"Disaster risk reduces yield by {(1 - disaster_factor.get(severity, 0.9)) * 100:.0f}%",
            "Consider drought-resistant varieties" if severity in ("medium", "high", "very_high") else "Standard varieties suitable",
            "Adjust planting date for optimal season" if seasonal_factor < 1.0 else "Good planting timing",
            "Improve soil organic matter for better resilience" if organic_matter < 3.0 else "Soil organic matter is adequate"
        ],
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

# ── List all routes ─────────────────────────────────────────
@app.route("/api/routes", methods=["GET"])
def list_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({"endpoint": rule.endpoint, "url": str(rule),
                        "methods": list(rule.methods - {"HEAD", "OPTIONS"})})
    return jsonify(routes)

print(f"\n📋 Registered routes:")
for rule in app.url_map.iter_rules():
    if rule.endpoint != "static":
        print(f"   {', '.join(rule.methods - {'HEAD','OPTIONS'})} {rule}")

# ============================================================
# I. DASHBOARD HTML (Enhanced with Disaster Features)
# ============================================================
DASHBOARD_HTML = textwrap.dedent("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EUS — Egyptian Energy Advisor + Disaster Resilience</title>
<style>
  :root { --bg: #0d1117; --card: #161b22; --accent: #58a6ff;
          --green: #3fb950; --border: #30363d; --text: #c9d1d9; --muted: #8b949e;
          --red: #f85149; --orange: #d29922; --purple: #bc8cff; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:'Segoe UI',sans-serif; background:var(--bg); color:var(--text);
         min-height:100vh; padding:2rem; }
  h1 { color:var(--accent); margin-bottom:0.5rem; }
  h2 { color:var(--green); margin:1.5rem 0 0.5rem; font-size:1.1rem; }
  h3 { color:var(--purple); margin:1rem 0 0.5rem; font-size:1rem; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:1.5rem; max-width:1200px; }
  .card { background:var(--card); border:1px solid var(--border);
          border-radius:12px; padding:1.5rem; }
  .card.full { grid-column:1/-1; }
  label { display:block; margin:0.5rem 0 0.25rem; color:var(--muted); font-size:0.85rem; }
  textarea, input, select { width:100%; background:var(--bg); color:var(--text);
    border:1px solid var(--border); border-radius:6px; padding:0.5rem;
    font-family:inherit; font-size:0.9rem; }
  textarea { min-height:120px; resize:vertical; }
  button { background:var(--accent); color:#fff; border:none; border-radius:6px;
           padding:0.6rem 1.5rem; cursor:pointer; font-size:0.95rem; margin-top:0.75rem; }
  button:hover { opacity:0.85; }
  button.green { background:var(--green); }
  button.red { background:var(--red); }
  button.orange { background:var(--orange); }
  pre { background:var(--bg); border:1px solid var(--border); border-radius:6px;
        padding:1rem; overflow-x:auto; font-size:0.82rem; max-height:400px; overflow-y:auto; }
  .badge { display:inline-block; padding:0.2rem 0.6rem; border-radius:4px;
           font-size:0.78rem; font-weight:600; }
  .badge.ok   { background:#1a4d1a; color:var(--green); }
  .badge.err  { background:#4d1a1a; color:var(--red); }
  .badge.warn { background:#4d3a1a; color:var(--orange); }
  .badge.info { background:#1a3a4d; color:var(--accent); }
  .status-row { display:flex; gap:1rem; align-items:center; margin-bottom:0.75rem; flex-wrap:wrap; }
  .notification { border-left:4px solid var(--accent); padding:1rem; margin:1rem 0;
                  background:rgba(88,166,255,0.1); border-radius:4px; }
  .notification.critical { border-left-color:var(--red); background:rgba(248,81,73,0.1); }
  .notification.warning { border-left-color:var(--orange); background:rgba(210,153,34,0.1); }
  .notification.info { border-left-color:var(--accent); background:rgba(88,166,255,0.1); }
  @media(max-width:768px){ .grid{grid-template-columns:1fr;} }
</style>
</head>
<body>
<h1>🌱 Eco-Urban-Space — Egyptian Energy Advisor</h1>
<p style="color:var(--muted)">Multimodal AI + Emissions Classifier + Disaster Resilience | Blossom-V7</p>

<div class="grid">
  <!-- Status -->
  <div class="card full">
    <h2>System Status</h2>
    <div class="status-row">
      <span id="healthBadge" class="badge err">checking…</span>
      <span id="disasterBadge" class="badge info">disaster data: loading</span>
      <span id="scopeLabel"></span>
    </div>
    <pre id="healthJson">Loading…</pre>
  </div>

  <!-- Scope -->
  <div class="card">
    <h2>Set Scope</h2>
    <select id="scopeSelect">
      <option>Scope 1 - Direct Emissions</option>
      <option selected>Scope 2 - Electricity Indirect</option>
      <option>Scope 3 - Value Chain</option>
    </select>
    <button onclick="setScope()">Apply Scope</button>
  </div>

  <!-- Model Info -->
  <div class="card">
    <h2>Model Info</h2>
    <pre id="modelInfo">—</pre>
  </div>

  <!-- NEW: Disaster Notification -->
  <div class="card full">
    <h2>🚨 Disaster Alert System</h2>
    <div class="status-row">
      <span id="locationStatus" class="badge info">📍 Detecting location…</span>
      <span id="disasterAlert" class="badge info">No active alerts</span>
    </div>
    <div class="grid">
      <div class="card">
        <h3>📍 Your Location</h3>
        <label for="latitude">Latitude:</label>
        <input type="number" id="latitude" value="30.0444" step="0.0001">
        <label for="longitude">Longitude:</label>
        <input type="number" id="longitude" value="31.2357" step="0.0001">
        <button onclick="getLocation()">🔄 Auto-detect</button>
      </div>
      <div class="card">
        <h3>🌾 Disaster Risk</h3>
        <pre id="disasterRisk">—</pre>
      </div>
    </div>
    <button class="red" onclick="checkDisasterAlert()">🔔 Check Alerts</button>
    <div id="notificationArea"></div>
  </div>

  <!-- Analyze Bill -->
  <div class="card full">
    <h2>📄 Analyze Energy Bill</h2>
    <label for="billText">Paste your energy bill data (text, CSV, or JSON):</label>
    <textarea id="billText" placeholder="e.g.&#10;Customer: Cairo Residential&#10;Month: July 2025&#10;Consumption: 850 kWh&#10;Rate: 1.25 EGP/kWh&#10;Total: 1062.50 EGP"></textarea>
    <button class="green" onclick="analyzeBill()">🔍 Analyze</button>
    <h2>Result</h2>
    <pre id="analysisResult">—</pre>
  </div>

  <!-- NEW: Disaster-Aware Recommendations -->
  <div class="card full">
    <h2>🌾 Disaster-Aware Agricultural Recommendations</h2>
    <div class="grid">
      <div class="card">
        <h3>🌍 Location & Date</h3>
        <label for="countryIso3">Country ISO3:</label>
        <input type="text" id="countryIso3" value="EGY" maxlength="3">
        <label for="currentDateTime">Current Date-Time:</label>
        <input type="datetime-local" id="currentDateTime">
        <button onclick="updateDateTime()">🔄 Now</button>
      </div>
      <div class="card">
        <h3>🧪 Soil Data</h3>
        <label for="soilPh">pH:</label>
        <input type="number" id="soilPh" value="7.0" step="0.1" min="0" max="14">
        <label for="organicMatter">Organic Matter (%):</label>
        <input type="number" id="organicMatter" value="2.5" step="0.1" min="0" max="10">
        <label for="nitrogen">Nitrogen (mg/kg):</label>
        <input type="number" id="nitrogen" value="25" step="1">
        <label for="phosphorus">Phosphorus (mg/kg):</label>
        <input type="number" id="phosphorus" value="15" step="1">
        <label for="potassium">Potassium (mg/kg):</label>
        <input type="number" id="potassium" value="20" step="1">
      </div>
    </div>
    <button class="green" onclick="getDisasterRecommendations()">🧠 Get Recommendations</button>
    <h2>Recommendations</h2>
    <pre id="disasterRecommendations">—</pre>
  </div>

  <!-- NEW: Yield Prediction -->
  <div class="card full">
    <h2>📈 Crop Yield Prediction</h2>
    <div class="grid">
      <div class="card">
        <h3>🌾 Crop Details</h3>
        <label for="cropType">Crop Type:</label>
        <select id="cropType">
          <option value="wheat">Wheat</option>
          <option value="corn">Corn</option>
          <option value="rice">Rice</option>
          <option value="cotton">Cotton</option>
          <option value="sugarcane">Sugarcane</option>
        </select>
        <label for="plantingDate">Planting Date:</label>
        <input type="date" id="plantingDate">
      </div>
      <div class="card">
        <h3>📊 Prediction Results</h3>
        <pre id="yieldPrediction">—</pre>
      </div>
    </div>
    <button class="green" onclick="predictYield()">🌱 Predict Yield</button>
  </div>

  <!-- Classify Emissions -->
  <div class="card full">
    <h2>🧮 Classify Emissions</h2>
    <label for="emissionsJson">JSON with feature values:</label>
    <textarea id="emissionsJson" placeholder='{"co2_eq_emissions": 83.5, "energy_consumption_kwh": 696}'></textarea>
    <button onclick="classifyEmissions()">Classify</button>
    <h2>Result</h2>
    <pre id="classifyResult">—</pre>
  </div>
</div>

<script>
const API = '';
async function api(path, opts={}) {
  const r = await fetch(API + path, {
    headers: {'Content-Type':'application/json'},
    ...opts
  });
  return r.json();
}

// Initialize date-time
function updateDateTime() {
  const now = new Date();
  const dtLocal = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
  document.getElementById('currentDateTime').value = dtLocal;
  document.getElementById('plantingDate').value = now.toISOString().split('T')[0];
}
updateDateTime();

// Get geolocation
function getLocation() {
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      pos => {
        document.getElementById('latitude').value = pos.coords.latitude.toFixed(4);
        document.getElementById('longitude').value = pos.coords.longitude.toFixed(4);
        document.getElementById('locationStatus').textContent =
          `📍 Location: ${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)}`;
        document.getElementById('locationStatus').className = 'badge ok';
      },
      err => {
        document.getElementById('locationStatus').textContent = `📍 Error: ${err.message}`;
        document.getElementById('locationStatus').className = 'badge err';
      }
    );
  } else {
    document.getElementById('locationStatus').textContent = '📍 Geolocation not supported';
    document.getElementById('locationStatus').className = 'badge err';
  }
}

async function refreshHealth() {
  try {
    const h = await api('/api/health');
    document.getElementById('healthJson').textContent = JSON.stringify(h, null, 2);
    const badge = document.getElementById('healthBadge');
    badge.textContent = h.ok ? '● ONLINE' : '● OFFLINE';
    badge.className = 'badge ' + (h.ok ? 'ok' : 'err');

    const disasterBadge = document.getElementById('disasterBadge');
    disasterBadge.textContent = h.disaster_data_available ?
      '🌍 Disaster data: available' : '🌍 Disaster data: unavailable';
    disasterBadge.className = 'badge ' + (h.disaster_data_available ? 'ok' : 'warn');

    document.getElementById('scopeLabel').textContent = 'Scope: ' + h.scope;
    document.getElementById('modelInfo').textContent =
      'Model: ' + h.model + '\\nBackend: ' + h.backend + '\\nModels: ' + JSON.stringify(h.available_models);
  } catch(e) {
    document.getElementById('healthJson').textContent = 'Error: ' + e;
  }
}

async function setScope() {
  const scope = document.getElementById('scopeSelect').value;
  const r = await api('/api/scope', {method:'POST', body:JSON.stringify({scope})});
  alert(r.success ? 'Scope set to: ' + r.scope : 'Error: ' + JSON.stringify(r));
  refreshHealth();
}

async function analyzeBill() {
  const bill_text = document.getElementById('billText').value;
  if (!bill_text) return alert('Enter bill text first.');
  document.getElementById('analysisResult').textContent = 'Analyzing…';
  try {
    const r = await api('/api/analyze-bill', {method:'POST', body:JSON.stringify({bill_text})});
    document.getElementById('analysisResult').textContent = JSON.stringify(r, null, 2);
  } catch(e) {
    document.getElementById('analysisResult').textContent = 'Error: ' + e;
  }
}

async function classifyEmissions() {
  const raw = document.getElementById('emissionsJson').value;
  try {
    const features = JSON.parse(raw);
    document.getElementById('classifyResult').textContent = 'Classifying…';
    const r = await api('/classify_emissions', {method:'POST', body:JSON.stringify(features)});
    document.getElementById('classifyResult').textContent = JSON.stringify(r, null, 2);
  } catch(e) {
    document.getElementById('classifyResult').textContent = 'Invalid JSON or error: ' + e;
  }
}

async function checkDisasterAlert() {
  const lat = parseFloat(document.getElementById('latitude').value);
  const lon = parseFloat(document.getElementById('longitude').value);

  document.getElementById('disasterRisk').textContent = 'Checking disaster risk…';

  try {
    const r = await api('/api/disaster-notification', {
      method: 'POST',
      body: JSON.stringify({
        latitude: lat,
        longitude: lon
      })
    });

    document.getElementById('disasterRisk').textContent = JSON.stringify(r.disaster_data, null, 2);

    // Display notification
    const area = document.getElementById('notificationArea');
    const notificationClass = r.alert_level === 'critical' ? 'critical' :
                             r.alert_level === 'warning' ? 'warning' : 'info';

    area.innerHTML = `
      <div class="notification ${notificationClass}">
        <h3>${r.title}</h3>
        <p>${r.message}</p>
        <h4>Recommendations:</h4>
        <ul>
          ${r.recommendations.map(rec => `<li>${rec}</li>`).join('')}
        </ul>
        <small>${r.timestamp}</small>
      </div>
    `;

    // Update alert badge
    const alertBadge = document.getElementById('disasterAlert');
    alertBadge.textContent = r.alert_level === 'critical' ? '🚨 CRITICAL ALERT' :
                           r.alert_level === 'warning' ? '⚠️ WARNING' : '✅ NO ALERT';
    alertBadge.className = 'badge ' + (r.alert_level === 'critical' ? 'err' :
                                      r.alert_level === 'warning' ? 'warn' : 'ok');

  } catch(e) {
    document.getElementById('disasterRisk').textContent = 'Error: ' + e;
  }
}

async function getDisasterRecommendations() {
  const countryIso3 = document.getElementById('countryIso3').value.toUpperCase();
  const lat = parseFloat(document.getElementById('latitude').value);
  const lon = parseFloat(document.getElementById('longitude').value);

  const soilData = {
    ph: parseFloat(document.getElementById('soilPh').value),
    organic_matter: parseFloat(document.getElementById('organicMatter').value),
    nitrogen: parseInt(document.getElementById('nitrogen').value),
    phosphorus: parseInt(document.getElementById('phosphorus').value),
    potassium: parseInt(document.getElementById('potassium').value),
    texture: "loam",
    drainage: "good"
  };

  document.getElementById('disasterRecommendations').textContent = 'Generating recommendations…';

  try {
    const r = await api('/api/disaster-recommendations', {
      method: 'POST',
      body: JSON.stringify({
        latitude: lat,
        longitude: lon,
        country_iso3: countryIso3,
        soil_data: soilData
      })
    });

    document.getElementById('disasterRecommendations').textContent = JSON.stringify(r, null, 2);
  } catch(e) {
    document.getElementById('disasterRecommendations').textContent = 'Error: ' + e;
  }
}

async function predictYield() {
  const countryIso3 = document.getElementById('countryIso3').value.toUpperCase();
  const cropType = document.getElementById('cropType').value;
  const plantingDate = document.getElementById('plantingDate').value;

  const soilData = {
    ph: parseFloat(document.getElementById('soilPh').value),
    organic_matter: parseFloat(document.getElementById('organicMatter').value),
    nitrogen: parseInt(document.getElementById('nitrogen').value),
    phosphorus: parseInt(document.getElementById('phosphorus').value),
    potassium: parseInt(document.getElementById('potassium').value)
  };

  document.getElementById('yieldPrediction').textContent = 'Predicting yield…';

  try {
    const r = await api('/api/yield-prediction', {
      method: 'POST',
      body: JSON.stringify({
        country_iso3: countryIso3,
        crop_type: cropType,
        planting_date: plantingDate,
        soil_data: soilData
      })
    });

    document.getElementById('yieldPrediction').textContent = JSON.stringify(r, null, 2);
  } catch(e) {
    document.getElementById('yieldPrediction').textContent = 'Error: ' + e;
  }
}

// Initialize
refreshHealth();
setInterval(refreshHealth, 30000);

// Auto-detect location on load
getLocation();
</script>
</body>
</html>
""")

with open("/content/index.html", "w") as f:
    f.write(DASHBOARD_HTML)
print("✅ Enhanced dashboard HTML written → /content/index.html")

# ============================================================
# J. LAUNCH FLASK + CLOUDFLARE TUNNEL
# ============================================================
# Kill any previous Flask / cloudflared
subprocess.run(["pkill", "-f", "cloudflared"], capture_output=True)
time.sleep(1)

# ── Start Flask in a thread ─────────────────────────────────
def run_flask():
    from werkzeug.serving import make_server
    server = make_server("0.0.0.0", FLASK_PORT, app)
    server.serve_forever()

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()
print(f"✅ Flask running on http://0.0.0.0:{FLASK_PORT}")

# ── Start Cloudflare Tunnel ────────────────────────────────
def launch_tunnel(port=FLASK_PORT, timeout=60):
    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    start = time.time()
    url = None
    while time.time() - start < timeout:
        line = proc.stderr.readline().decode(errors="replace")
        match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
        if match:
            url = match.group()
            break
    return proc, url

tunnel_proc, tunnel_url = launch_tunnel()

if tunnel_url:
    print(f"\n{'='*64}")
    print(f"✅ Dashboard live at: {tunnel_url}")
    print(f"{'='*64}")
else:
    print("⚠  Could not extract tunnel URL. Check cloudflared.")
    print("   Flask is still accessible from Colab's port-forwarding.")

print("\n⚠  Colab free sessions cap at ~12 h and time out when idle.")
print("   The URL dies with the session; re-run Cell 2 to get a new one.")

# ============================================================
# K. VERIFY ENDPOINTS END-TO-END
# ============================================================
time.sleep(2)   # let Flask settle

print("\n🔍 Verification:")
base = f"http://localhost:{FLASK_PORT}"

# Health
r = requests.get(f"{base}/api/health", timeout=10)
h = r.json()
print(f"→ /api/health  ok={h['ok']}  disaster_data={h.get('disaster_data_available')}")

# Scope
r = requests.get(f"{base}/api/scope")
print(f"→ /api/scope   {r.json()}")

# NEW: Disaster loss
r = requests.get(f"{base}/api/disaster-loss?country_iso3=EGY&year=2023")
disaster_data = r.json()
print(f"→ /api/disaster-loss  EGY 2023: ${disaster_data.get('loss_value_usd', 'N/A')} USD")

# NEW: Disaster notification
r = requests.post(f"{base}/api/disaster-notification", json={
    "latitude": 30.0444,
    "longitude": 31.2357
}, timeout=30)
notification = r.json()
print(f"→ /api/disaster-notification  level={notification.get('alert_level')}")

# NEW: Disaster recommendations
r = requests.post(f"{base}/api/disaster-recommendations", json={
    "latitude": 30.0444,
    "longitude": 31.2357,
    "country_iso3": "EGY",
    "soil_data": {"ph": 7.0, "organic_matter": 2.5}
}, timeout=60)
recs = r.json()
print(f"→ /api/disaster-recommendations  severity={recs.get('disaster_assessment', {}).get('severity_level')}")

# NEW: Yield prediction
r = requests.post(f"{base}/api/yield-prediction", json={
    "country_iso3": "EGY",
    "crop_type": "wheat",
    "planting_date": "2025-10-15",
    "soil_data": {"ph": 7.0, "organic_matter": 2.5}
}, timeout=30)
yield_pred = r.json()
print(f"→ /api/yield-prediction  yield={yield_pred.get('soil_adjusted_yield_kg_ha', 'N/A')} kg/ha")

# Routes
r = requests.get(f"{base}/api/routes")
print(f"→ /api/routes  {[x['url'] for x in r.json() if 'disaster' in x['url'] or 'yield' in x['url']]}")

# ============================================================
# L. KEEP-ALIVE (prevents Colab idle timeout)
# ============================================================
print("\n🔄 Keep-alive running. Close cell output or press Ctrl+C to stop.")
try:
    while True:
        time.sleep(60)
        # Periodic health ping
        try:
            requests.get(f"{base}/api/health", timeout=5)
        except:
            pass
except KeyboardInterrupt:
    print("\n🛑 Stopped by user.")
