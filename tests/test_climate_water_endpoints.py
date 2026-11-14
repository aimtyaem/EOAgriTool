"""Tests for Open-Meteo-backed climate and water endpoints."""
import pytest

from backend import routes
from backend.routes import create_app


@pytest.fixture
def app():
    routes._climate_cache.clear()
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.mark.asyncio
async def test_climate_invalid_region_400(app):
    async with app.test_client() as client:
        response = await client.get('/climate_data?region=mars')
        assert response.status_code == 400
        assert (await response.get_json())['code'] == 'INVALID_REGION'


@pytest.mark.asyncio
async def test_climate_invalid_horizon_400(app):
    async with app.test_client() as client:
        response = await client.get('/climate_data?horizon=2y')
        assert response.status_code == 400
        assert (await response.get_json())['code'] == 'INVALID_HORIZON'


@pytest.fixture
def forecast_payload():
    return {'hourly': {
        'time': [f'2026-01-01T{hour:02d}:00' for hour in range(4)],
        'temperature_2m': [20.0, 20.5, 21.0, 21.5],
        'precipitation': [0.0, 0.2, 0.0, 0.5],
        'wind_speed_10m': [2.0, 2.5, 3.0, 3.5],
        'soil_moisture_0_to_7cm': [0.30, 0.31, 0.29, 0.30],
        'et0_fao_evapotranspiration': [1.0, 1.2, 1.1, 1.3],
    }}


@pytest.mark.asyncio
async def test_climate_success_shape(app, httpx_mock, forecast_payload):
    httpx_mock.add_response(url=routes.OPEN_METEO_FORECAST_URL, json=forecast_payload)
    async with app.test_client() as client:
        response = await client.get('/climate_data?region=nile_delta&horizon=72h')
        body = await response.get_json()
    assert response.status_code == 200
    assert body['source'] == 'open-meteo'
    assert body['stale'] is False
    assert set(body['data']) == {'temperature', 'rainfall', 'wind', 'timestamps', 'current'}
    assert body['data']['temperature'][0] == 20.0


@pytest.mark.asyncio
async def test_climate_upstream_failure_returns_stale_200(app, httpx_mock, forecast_payload):
    httpx_mock.add_response(url=routes.OPEN_METEO_FORECAST_URL, json=forecast_payload)
    async with app.test_client() as client:
        first = await client.get('/climate_data?region=sahel&horizon=72h')
    assert first.status_code == 200
    routes._climate_cache[('sahel', '72h')] = (0, (await first.get_json()))
    httpx_mock.add_exception(RuntimeError('upstream down'), url=routes.OPEN_METEO_FORECAST_URL)
    async with app.test_client() as client:
        response = await client.get('/climate_data?region=sahel&horizon=72h')
        body = await response.get_json()
    assert response.status_code == 200
    assert body['stale'] is True
    assert body['source'] == 'cache'
    assert body['data'] is not None


@pytest.mark.asyncio
async def test_water_success_shape(app, httpx_mock, forecast_payload):
    httpx_mock.add_response(url=routes.OPEN_METEO_FORECAST_URL, json=forecast_payload)
    async with app.test_client() as client:
        response = await client.get('/water_data?region=nile_delta')
        body = await response.get_json()
    assert response.status_code == 200
    assert body['source'] == 'open-meteo'
    assert {'soil_moisture_avg', 'et0_total_mm', 'rain_total_mm', 'irrigation_deficit_mm', 'series'} <= set(body['data'])
    assert body['data']['soil_moisture_avg'] == 0.3


@pytest.mark.asyncio
async def test_water_upstream_failure_returns_stale_200(app, httpx_mock, forecast_payload):
    httpx_mock.add_response(url=routes.OPEN_METEO_FORECAST_URL, json=forecast_payload)
    async with app.test_client() as client:
        first = await client.get('/water_data?region=mediterranean')
    routes._climate_cache[('mediterranean', 'water')] = (0, (await first.get_json()))
    httpx_mock.add_exception(RuntimeError('upstream down'), url=routes.OPEN_METEO_FORECAST_URL)
    async with app.test_client() as client:
        response = await client.get('/water_data?region=mediterranean')
        body = await response.get_json()
    assert response.status_code == 200
    assert body['stale'] is True
    assert body['source'] == 'cache'


@pytest.mark.asyncio
async def test_cache_hit_does_not_call_upstream(app, httpx_mock, forecast_payload):
    httpx_mock.add_response(url=routes.OPEN_METEO_FORECAST_URL, json=forecast_payload)
    async with app.test_client() as client:
        first = await client.get('/climate_data?region=southeast_asia&horizon=72h')
        second = await client.get('/climate_data?region=southeast_asia&horizon=72h')
    assert first.status_code == second.status_code == 200
    assert (await second.get_json())['source'] == 'open-meteo'
    assert len(httpx_mock.get_requests()) == 1
