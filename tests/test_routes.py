"""Smoke tests for EOAgriTool routes and recommendation engine."""

import json
import pytest
from backend.recommend.engine import generate_recommendations, parse_energy_bill


# ────────────────────────────────────────────────────────────
# Recommendation Engine Tests
# ────────────────────────────────────────────────────────────

class TestGenerateRecommendations:
    def test_high_energy_usage(self):
        recs = generate_recommendations({"usage_kwh": 1200, "rate_per_kwh": 0.18})
        assert any(r["category"] == "energy" and "High Energy" in r["title"] for r in recs)

    def test_high_rate(self):
        recs = generate_recommendations({"rate_per_kwh": 0.22, "usage_kwh": 800})
        assert any("Above-Average" in r["title"] for r in recs)

    def test_high_irrigation(self):
        recs = generate_recommendations({"irrigation_mm": 1100})
        assert any(r["category"] == "water" and "Irrigation" in r["title"] for r in recs)

    def test_rainfall_deficit(self):
        recs = generate_recommendations({"deficit_mm": -35})
        assert any("Rainfall Deficit" in r["title"] for r in recs)

    def test_alkaline_soil(self):
        recs = generate_recommendations({"pH": 8.2})
        assert any(r["category"] == "soil" and "Alkaline" in r["title"] for r in recs)

    def test_low_om(self):
        recs = generate_recommendations({"organic_matter_pct": 0.9})
        assert any("Organic Matter" in r["title"] for r in recs)

    def test_high_carbon(self):
        recs = generate_recommendations({"carbon_footprint_kg": 8000})
        assert any(r["category"] == "carbon" for r in recs)

    def test_legume_after_wheat(self):
        recs = generate_recommendations({}, {"previous_crop": "wheat"})
        assert any("Legume" in r["title"] for r in recs)

    def test_no_issues(self):
        recs = generate_recommendations({"usage_kwh": 300, "rate_per_kwh": 0.10})
        assert any("No Critical" in r["title"] for r in recs)

    def test_all_priorities_present(self):
        priorities = {r["priority"] for r in generate_recommendations({
            "usage_kwh": 1500, "irrigation_mm": 1200, "pH": 8.3, "organic_matter_pct": 0.8
        })}
        assert "critical" in priorities or "high" in priorities


# ────────────────────────────────────────────────────────────
# Energy Bill Parser Tests
# ────────────────────────────────────────────────────────────

class TestParseEnergyBill:
    def test_basic_text_bill(self):
        text = "Total: $145.60\nUsage: 890 kWh\nBilling period: 01/15/2025 to 02/14/2025"
        result = parse_energy_bill(text, "text")
        assert result["total"] == 145.60
        assert result["usage_kwh"] == 890.0
        assert result["period_start"] == "01/15/2025"
        assert result["period_end"] == "02/14/2025"
        assert result["rate_per_kwh"] is not None

    def test_eur_currency(self):
        text = "Amount due: €98,50\nVerbrauch: 450 kWh"
        result = parse_energy_bill(text, "text")
        assert result["currency"] == "EUR"

    def test_no_data(self):
        result = parse_energy_bill("random text without bill data", "text")
        assert result["total"] is None
        assert len(result["warnings"]) > 0

    def test_comma_in_numbers(self):
        text = "Total: $1,234.56\nUsage: 5,678 kWh"
        result = parse_energy_bill(text, "text")
        assert result["total"] == 1234.56
        assert result["usage_kwh"] == 5678.0

    def test_rate_calculation(self):
        text = "Total: $100.00\nUsage: 500 kWh"
        result = parse_energy_bill(text, "text")
        assert result["rate_per_kwh"] == 0.20

    def test_html_format(self):
        html = "<html><body><p>Total: $75.00</p><p>Usage: 300 kWh</p></body></html>"
        result = parse_energy_bill(html, "html")
        assert result["total"] == 75.00
        assert result["usage_kwh"] == 300.0

    def test_egp_currency(self):
        text = "Total: EGP 2500.00\nUsage: 1200 kWh"
        result = parse_energy_bill(text, "text")
        assert result["currency"] == "EGP"