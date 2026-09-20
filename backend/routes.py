"""
backend/routes.py — All HTTP routes and Azure OpenAI integration.

This module provides:
  - Static asset serving and SPA index
  - Azure OpenAI chat completions (streaming + non-streaming)
  - Azure Functions tool calling (remote function calls)
  - CosmosDB conversation history CRUD
  - EOAgriTool domain endpoints (sustainability, energy, recommendations, vtracker)
  - Health check and frontend settings
"""

from __future__ import annotations

import copy
import json
import os
import logging
import uuid
import asyncio
from typing import Any

import httpx
from quart import (
    Blueprint,
    Quart,
    jsonify,
    make_response,
    request,
    send_from_directory,
    render_template,
    current_app,
)
from quart_cors import cors

from openai import AsyncAzureOpenAI
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider

from backend.auth.auth_utils import get_authenticated_user_details
from backend.security.ms_defender_utils import get_msdefender_user_json
from backend.history.cosmosdbservice import CosmosConversationClient
from backend.settings import (
    app_settings,
    MINIMUM_SUPPORTED_AZURE_OPENAI_PREVIEW_API_VERSION,
)
from backend.utils import (
    format_as_ndjson,
    format_stream_response,
    format_non_streaming_response,
    convert_to_pf_format,
    format_pf_non_streaming_response,
)
from backend.recommend.engine import generate_recommendations, parse_energy_bill

logger = logging.getLogger("eoagritool.routes")

# ────────────────────────────────────────────────────────────
# Blueprint
# ────────────────────────────────────────────────────────────

bp = Blueprint("routes", __name__, static_folder="static", template_folder="static")

# ────────────────────────────────────────────────────────────
# Configuration constants
# ────────────────────────────────────────────────────────────

USER_AGENT = os.environ.get("APP_USER_AGENT", "EOAgriTool/AsyncAzureOpenAI/2.0.0")
MS_DEFENDER_ENABLED = os.environ.get("MS_DEFENDER_ENABLED", "true").lower() == "true"
COSMOS_INIT_TIMEOUT_SECONDS = int(os.environ.get("COSMOS_INIT_TIMEOUT_SECONDS", "30"))
MAX_CONVERSATION_MESSAGES_FOR_TITLE = int(
    os.environ.get("MAX_CONVERSATION_MESSAGES_FOR_TITLE", "10")
)

SUSTAINABILITY_GOALS = {
    "reduce_carbon_footprint",
    "energy_efficiency",
    "water_conservation",
    "waste_reduction",
    "sustainable_agriculture",
    "renewable_energy",
    "biodiversity",
    "climate_resilience",
}

VTRACKER_API_URL = os.environ.get(
    "VTRACKER_API_URL",
    "https://eoagritool-cwfzfndaazauawex.canadacentral-01.azurewebsites.net/vtracker_data.json",
)

# ────────────────────────────────────────────────────────────
# Application factory
# ────────────────────────────────────────────────────────────

def create_app() -> Quart:
    """Create and configure the Quart application."""

    app = Quart(__name__)
    cors(app, allow_origin="*", allow_methods=["GET", "POST", "DELETE", "OPTIONS"])

    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB

    # State initialised before serving
    app.azure_openai_client: AsyncAzureOpenAI | None = None
    app.azure_credential: DefaultAzureCredential | None = None
    app.cosmos_conversation_client: CosmosConversationClient | None = None
    app.azure_openai_tools: list = []
    app.azure_openai_available_tools: list = []

    # Signal for CosmosDB readiness (set even on failure so routes don't deadlock)
    app.cosmos_db_ready = asyncio.Event()

    app.register_blueprint(bp)

    @app.before_serving
    async def _startup():
        await _init_azure_credential(app)
        await _init_openai_client(app)
        await _init_cosmosdb_client(app)

    @app.after_serving
    async def _shutdown():
        if app.azure_openai_client:
            await app.azure_openai_client.close()
            logger.info("Azure OpenAI client closed.")
        if app.azure_credential:
            await app.azure_credential.close()
            logger.info("Azure credential closed.")

    return app


# ────────────────────────────────────────────────────────────
# Startup helpers
# ────────────────────────────────────────────────────────────

async def _init_azure_credential(app: Quart) -> None:
    """Initialise DefaultAzureCredential if no API key is configured."""
    if not app_settings.azure_openai.key:
        logger.info("No AZURE_OPENAI_KEY — using Azure Entra ID auth")
        app.azure_credential = DefaultAzureCredential()
    else:
        app.azure_credential = None


async def _init_openai_client(app: Quart) -> None:
    """Create a single AsyncAzureOpenAI client for the app lifetime."""
    try:
        # --- API version check ---
        if (
            app_settings.azure_openai.preview_api_version
            < MINIMUM_SUPPORTED_AZURE_OPENAI_PREVIEW_API_VERSION
        ):
            raise ValueError(
                f"Minimum supported Azure OpenAI preview API version is "
                f"'{MINIMUM_SUPPORTED_AZURE_OPENAI_PREVIEW_API_VERSION}'"
            )

        # --- Endpoint ---
        if not app_settings.azure_openai.endpoint and not app_settings.azure_openai.resource:
            raise ValueError("AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_RESOURCE is required")

        endpoint = app_settings.azure_openai.endpoint or (
            f"https://{app_settings.azure_openai.resource}.openai.azure.com/"
        )

        # --- Auth ---
        aoai_api_key = app_settings.azure_openai.key
        ad_token_provider = None
        if not aoai_api_key and app.azure_credential:
            ad_token_provider = get_bearer_token_provider(
                app.azure_credential,
                "https://cognitiveservices.azure.com/.default",
            )

        # --- Deployment ---
        deployment = app_settings.azure_openai.model
        if not deployment:
            raise ValueError("AZURE_OPENAI_MODEL is required")

        # --- Remote function-call tools ---
        if app_settings.azure_openai.function_call_azure_functions_enabled:
            await _fetch_azure_function_tools(app)

        # --- Client ---
        app.azure_openai_client = AsyncAzureOpenAI(
            api_version=app_settings.azure_openai.preview_api_version,
            api_key=aoai_api_key,
            azure_ad_token_provider=ad_token_provider,
            default_headers={"x-ms-useragent": USER_AGENT},
            azure_endpoint=endpoint,
        )
        logger.info("Azure OpenAI client initialised (model=%s)", deployment)

    except Exception:
        logger.exception("Failed to initialise Azure OpenAI client")
        app.azure_openai_client = None
        # Non-fatal: the app can still serve static assets and non-LLM routes


async def _fetch_azure_function_tools(app: Quart) -> None:
    """Fetch tool definitions from the Azure Functions endpoint."""
    try:
        url = (
            f"{app_settings.azure_openai.function_call_azure_functions_tools_base_url}"
            f"?code={app_settings.azure_openai.function_call_azure_functions_tools_key}"
        )
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
        resp.raise_for_status()
        tools = resp.json()
        app.azure_openai_tools.extend(tools)
        app.azure_openai_available_tools.extend(
            t["function"]["name"] for t in tools
        )
        logger.info("Loaded %d Azure Function tool(s)", len(tools))
    except Exception:
        logger.exception("Failed to fetch Azure Function tools metadata")


async def _init_cosmosdb_client(app: Quart) -> None:
    """Initialise CosmosDB client; set the readiness event regardless of outcome."""
    try:
        if not app_settings.chat_history:
            logger.debug("CosmosDB not configured — skipping")
            app.cosmos_conversation_client = None
            return

        cosmos_endpoint = (
            f"https://{app_settings.chat_history.account}.documents.azure.com:443/"
        )

        if app_settings.chat_history.account_key:
            credential = app_settings.chat_history.account_key
        else:
            if not app.azure_credential:
                app.azure_credential = DefaultAzureCredential()
            credential = app.azure_credential

        app.cosmos_conversation_client = CosmosConversationClient(
            cosmosdb_endpoint=cosmos_endpoint,
            credential=credential,
            database_name=app_settings.chat_history.database,
            container_name=app_settings.chat_history.conversations_container,
            enable_message_feedback=app_settings.chat_history.enable_feedback,
        )
        logger.info("CosmosDB client initialised")

    except Exception:
        logger.exception("Failed to initialise CosmosDB client")
        app.cosmos_conversation_client = None

    finally:
        # ALWAYS set the event so awaiting routes don't deadlock
        app.cosmos_db_ready.set()


# ────────────────────────────────────────────────────────────
# Frontend settings (computed once at startup; read-only after)
# ────────────────────────────────────────────────────────────

_frontend_settings: dict = {}


def _compute_frontend_settings() -> dict:
    return {
        "auth_enabled": app_settings.base_settings.auth_enabled,
        "feedback_enabled": (
            app_settings.chat_history
            and app_settings.chat_history.enable_feedback
        ),
        "ui": {
            "title": app_settings.ui.title,
            "logo": app_settings.ui.logo,
            "chat_logo": app_settings.ui.chat_logo or app_settings.ui.logo,
            "chat_title": app_settings.ui.chat_title,
            "chat_description": app_settings.ui.chat_description,
            "show_share_button": app_settings.ui.show_share_button,
            "show_chat_history_button": app_settings.ui.show_chat_history_button,
        },
        "sanitize_answer": app_settings.base_settings.sanitize_answer,
        "oyd_enabled": app_settings.base_settings.datasource_type,
    }


# ────────────────────────────────────────────────────────────
# Static / SPA routes
# ────────────────────────────────────────────────────────────

@bp.route("/")
async def index():
    return await render_template(
        "index.html",
        title=app_settings.ui.title,
        favicon=app_settings.ui.favicon,
    )


@bp.route("/favicon.ico")
async def favicon():
    return await bp.send_static_file("favicon.ico")


@bp.route("/assets/<path:path>")
async def assets(path: str):
    return await send_from_directory("static/assets", path)


# ────────────────────────────────────────────────────────────
# Health check
# ────────────────────────────────────────────────────────────

@bp.route("/health", methods=["GET"])
async def health_check():
    """Liveness / readiness probe for container orchestration."""
    checks = {
        "openai": current_app.azure_openai_client is not None,
        "cosmosdb": current_app.cosmos_conversation_client is not None,
    }
    status = 200 if all(checks.values()) else 503
    return jsonify({"status": "healthy" if status == 200 else "degraded", "checks": checks}), status


# ────────────────────────────────────────────────────────────
# Frontend settings
# ────────────────────────────────────────────────────────────

@bp.route("/frontend_settings", methods=["GET"])
async def get_frontend_settings():
    try:
        if not _frontend_settings:
            _frontend_settings.update(_compute_frontend_settings())
        return jsonify(_frontend_settings), 200
    except Exception:
        logger.exception("Exception in /frontend_settings")
        return jsonify({"error": "Failed to compute frontend settings", "code": "SETTINGS_ERROR"}), 500


# ────────────────────────────────────────────────────────────
# Model argument preparation
# ────────────────────────────────────────────────────────────

def _prepare_model_args(request_body: dict, request_headers: dict) -> dict:
    """
    Build the keyword arguments dict for ``azure_openai_client.chat.completions.create``.

    Includes:
      - System message injection
      - Message formatting (user / assistant / function / tool)
      - MS Defender user JSON (if enabled)
      - Data-source payload (if configured)
      - Secret redaction for logging
    """
    request_messages = request_body.get("messages", [])
    messages: list[dict] = []

    # System message when no data-source (data-source injects its own system prompt)
    if not app_settings.datasource:
        messages.append({
            "role": "system",
            "content": app_settings.azure_openai.system_message,
        })

    for message in request_messages:
        if not message:
            continue
        role = message.get("role")
        match role:
            case "user":
                messages.append({
                    "role": role,
                    "content": message["content"],
                })
            case "assistant" | "function" | "tool":
                entry: dict[str, Any] = {"role": role}
                if "name" in message:
                    entry["name"] = message["name"]
                if "function_call" in message:
                    entry["function_call"] = message["function_call"]
                entry["content"] = message.get("content")
                if "context" in message:
                    try:
                        entry["context"] = json.loads(message["context"])
                    except (json.JSONDecodeError, TypeError):
                        logger.warning("Failed to parse context JSON for message")
                messages.append(entry)
            case _:
                logger.warning("Dropping message with unrecognised role: %s", role)

    # MS Defender user JSON
    user_json = None
    if MS_DEFENDER_ENABLED:
        try:
            auth_details = get_authenticated_user_details(request_headers)
            conversation_id = request_body.get("conversation_id")
            user_json = get_msdefender_user_json(
                auth_details, request_headers, conversation_id, app_settings.ui.title
            )
        except Exception:
            logger.warning("MS Defender user JSON generation failed", exc_info=True)

    model_args = {
        "messages": messages,
        "temperature": app_settings.azure_openai.temperature,
        "max_tokens": app_settings.azure_openai.max_tokens,
        "top_p": app_settings.azure_openai.top_p,
        "stop": app_settings.azure_openai.stop_sequence,
        "stream": app_settings.azure_openai.stream,
        "model": app_settings.azure_openai.model,
        "user": user_json,
    }

    # Attach tools / data-sources only when the last message is from the user
    if messages and messages[-1]["role"] == "user":
        if (
            app_settings.azure_openai.function_call_azure_functions_enabled
            and current_app.azure_openai_tools
        ):
            model_args["tools"] = current_app.azure_openai_tools

        if app_settings.datasource:
            model_args["extra_body"] = {
                "data_sources": [
                    app_settings.datasource.construct_payload_configuration(request=request)
                ]
            }

    # Redact secrets for debug logging
    _log_model_args(model_args)

    return model_args


def _log_model_args(model_args: dict) -> None:
    """Log model args with secrets redacted."""
    clean = copy.deepcopy(model_args)
    secret_keys = {"key", "connection_string", "embedding_key", "encoded_api_key", "api_key"}

    if clean.get("extra_body"):
        try:
            params = clean["extra_body"]["data_sources"][0]["parameters"]
            for sk in secret_keys:
                if params.get(sk):
                    params[sk] = "*****"
            auth = params.get("authentication", {})
            for f in auth:
                if f in secret_keys:
                    auth[f] = "*****"
            emb_dep = params.get("embedding_dependency", {})
            if "authentication" in emb_dep:
                for f in emb_dep["authentication"]:
                    if f in secret_keys:
                        emb_dep["authentication"][f] = "*****"
        except (KeyError, IndexError):
            pass

    logger.debug("REQUEST BODY: %s", json.dumps(clean, indent=4, default=str))


# ────────────────────────────────────────────────────────────
# Azure Function remote calls
# ────────────────────────────────────────────────────────────

async def _openai_remote_azure_function_call(function_name: str, function_args: str) -> str:
    """Invoke an Azure Function tool and return its response text."""
    if not app_settings.azure_openai.function_call_azure_functions_enabled:
        raise ValueError("Azure Function calling is not enabled")

    url = (
        f"{app_settings.azure_openai.function_call_azure_functions_tool_base_url}"
        f"?code={app_settings.azure_openai.function_call_azure_functions_tools_key}"
    )
    body = {
        "tool_name": function_name,
        "tool_arguments": json.loads(function_args),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=body)
    resp.raise_for_status()
    return resp.text


# ────────────────────────────────────────────────────────────
# Chat request pipeline
# ────────────────────────────────────────────────────────────

async def _send_chat_request(request_body: dict, request_headers: dict):
    """
    Send a chat completion request to Azure OpenAI.

    Returns
    -------
    tuple(response, apim_request_id)
    """
    # Filter out orphaned tool messages (tool messages whose tool_call_id
    # doesn't match any assistant tool_call in the conversation).
    # This prevents "tool message without preceding tool_call" API errors.
    filtered = _filter_orphaned_tool_messages(request_body.get("messages", []))
    request_body["messages"] = filtered

    model_args = _prepare_model_args(request_body, request_headers)

    client = current_app.azure_openai_client
    if not client:
        raise RuntimeError("Azure OpenAI client is not initialised")

    try:
        raw_response = await client.chat.completions.with_raw_response.create(**model_args)
        response = raw_response.parse()
        apim_request_id = raw_response.headers.get("apim-request-id")
        return response, apim_request_id
    except Exception:
        logger.exception("Exception in _send_chat_request")
        raise


def _filter_orphaned_tool_messages(messages: list[dict]) -> list[dict]:
    """
    Remove tool-role messages that have no matching assistant tool_call.

    Previous code removed ALL tool messages, which broke multi-turn
    function calling. This version only removes orphans.
    """
    # Collect all tool_call_ids from assistant messages
    valid_tool_call_ids: set[str] = set()
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                if tc.get("id"):
                    valid_tool_call_ids.add(tc["id"])

    filtered: list[dict] = []
    for msg in messages:
        if msg.get("role") == "tool":
            tc_id = msg.get("tool_call_id")
            if tc_id and tc_id in valid_tool_call_ids:
                filtered.append(msg)
            else:
                logger.debug("Dropping orphaned tool message (tool_call_id=%s)", tc_id)
        else:
            filtered.append(msg)

    return filtered


async def _process_function_call(response) -> list[dict] | None:
    """Execute any function calls in a non-streaming response."""
    response_message = response.choices[0].message
    if not response_message.tool_calls:
        return None

    messages: list[dict] = []
    for tool_call in response_message.tool_calls:
        if tool_call.function.name not in current_app.azure_openai_available_tools:
            logger.warning("Unknown tool: %s — skipping", tool_call.function.name)
            continue

        function_response = await _openai_remote_azure_function_call(
            tool_call.function.name, tool_call.function.arguments
        )

        messages.append({
            "role": response_message.role,
            "function_call": {
                "name": tool_call.function.name,
                "arguments": tool_call.function.arguments,
            },
            "content": None,
        })
        messages.append({
            "role": "function",
            "name": tool_call.function.name,
            "content": function_response,
        })

    return messages if messages else None


async def _complete_chat_request(request_body: dict, request_headers: dict) -> dict:
    """Non-streaming chat completion (with optional function calling)."""
    if app_settings.base_settings.use_promptflow:
        resp = await _promptflow_request(request_body)
        history_metadata = request_body.get("history_metadata", {})
        return format_pf_non_streaming_response(
            resp,
            history_metadata,
            app_settings.promptflow.response_field_name,
            app_settings.promptflow.citations_field_name,
        )

    response, apim_request_id = await _send_chat_request(request_body, request_headers)
    history_metadata = request_body.get("history_metadata", {})
    result = format_non_streaming_response(response, history_metadata, apim_request_id)

    # Handle function calls
    if app_settings.azure_openai.function_call_azure_functions_enabled:
        function_response = await _process_function_call(response)
        if function_response:
            request_body["messages"].extend(function_response)
            response, apim_request_id = await _send_chat_request(request_body, request_headers)
            history_metadata = request_body.get("history_metadata", {})
            result = format_non_streaming_response(response, history_metadata, apim_request_id)

    return result


# ────────────────────────────────────────────────────────────
# Streaming function-call state machine
# ────────────────────────────────────────────────────────────

class _FunctionCallStreamState:
    """Accumulates tool-call chunks across a streaming response."""

    def __init__(self) -> None:
        self.tool_calls: list[dict] = []
        self.tool_name: str = ""
        self.tool_arguments_stream: str = ""
        self.current_tool_call: dict | None = None
        self.function_messages: list[dict] = []
        self.streaming_state: str = "INITIAL"  # INITIAL | STREAMING | COMPLETED


async def _process_function_call_stream(
    chunk,
    state: _FunctionCallStreamState,
) -> str:
    """
    Process a single streaming chunk for function calls.

    Returns the current streaming_state.
    """
    if not hasattr(chunk, "choices") or not chunk.choices:
        return state.streaming_state

    delta = chunk.choices[0].delta

    if delta.tool_calls and state.streaming_state in ("INITIAL", "STREAMING"):
        state.streaming_state = "STREAMING"
        for tc_chunk in delta.tool_calls:
            if tc_chunk.id:
                # Flush the previous tool call
                if state.current_tool_call:
                    state.tool_arguments_stream += tc_chunk.function.arguments or ""
                    state.current_tool_call["tool_arguments"] = state.tool_arguments_stream
                    state.tool_arguments_stream = ""
                    state.tool_name = ""
                    state.tool_calls.append(state.current_tool_call)

                state.current_tool_call = {
                    "tool_id": tc_chunk.id,
                    "tool_name": (
                        tc_chunk.function.name
                        if not state.tool_name and tc_chunk.function.name
                        else state.tool_name
                    ),
                }
            else:
                state.tool_arguments_stream += tc_chunk.function.arguments or ""

    elif delta.tool_calls is None and state.streaming_state == "STREAMING":
        # Stream completed — flush and execute
        if state.current_tool_call:
            state.current_tool_call["tool_arguments"] = state.tool_arguments_stream
            state.tool_calls.append(state.current_tool_call)

        for tool_call in state.tool_calls:
            tool_response = await _openai_remote_azure_function_call(
                tool_call["tool_name"], tool_call["tool_arguments"]
            )
            state.function_messages.append({
                "role": "assistant",
                "function_call": {
                    "name": tool_call["tool_name"],
                    "arguments": tool_call["tool_arguments"],
                },
                "content": None,
            })
            state.function_messages.append({
                "tool_call_id": tool_call["tool_id"],
                "role": "function",
                "name": tool_call["tool_name"],
                "content": tool_response,
            })

        state.streaming_state = "COMPLETED"

    return state.streaming_state


async def _stream_chat_request(request_body: dict, request_headers: dict):
    """Streaming chat completion (with optional function calling)."""
    response, apim_request_id = await _send_chat_request(request_body, request_headers)
    history_metadata = request_body.get("history_metadata", {})

    async def generate(apim_request_id, history_metadata):
        if app_settings.azure_openai.function_call_azure_functions_enabled:
            state = _FunctionCallStreamState()
            async for chunk in response:
                stream_state = await _process_function_call_stream(chunk, state)

                # No function call — assistant text response
                if stream_state == "INITIAL":
                    yield format_stream_response(chunk, history_metadata, apim_request_id)

                # Function call completed — send final answer
                if stream_state == "COMPLETED":
                    request_body["messages"].extend(state.function_messages)
                    fn_response, fn_apim_id = await _send_chat_request(
                        request_body, request_headers
                    )
                    async for fn_chunk in fn_response:
                        yield format_stream_response(fn_chunk, history_metadata, fn_apim_id)
        else:
            async for chunk in response:
                yield format_stream_response(chunk, history_metadata, apim_request_id)

    return generate(apim_request_id=apim_request_id, history_metadata=history_metadata)


# ────────────────────────────────────────────────────────────
# PromptFlow
# ────────────────────────────────────────────────────────────

async def _promptflow_request(request_body: dict) -> dict:
    """Send a request to a PromptFlow endpoint."""
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {app_settings.promptflow.api_key}",
        }
        timeout = float(app_settings.promptflow.response_timeout)
        if timeout <= 0:
            raise ValueError(f"Invalid PromptFlow timeout: {timeout}")

        logger.debug("PromptFlow timeout: %.1fs", timeout)

        async with httpx.AsyncClient(timeout=timeout) as client:
            pf_obj = convert_to_pf_format(
                request_body,
                app_settings.promptflow.request_field_name,
                app_settings.promptflow.response_field_name,
            )
            resp = await client.post(
                app_settings.promptflow.endpoint,
                json={
                    app_settings.promptflow.request_field_name: pf_obj[-1]["inputs"][
                        app_settings.promptflow.request_field_name
                    ],
                    "chat_history": pf_obj[:-1],
                },
                headers=headers,
            )
        resp.raise_for_status()
        result = resp.json()
        result["id"] = request_body["messages"][-1]["id"]
        return result
    except Exception:
        logger.exception("PromptFlow request failed")
        raise


# ────────────────────────────────────────────────────────────
# Conversation pipeline entry point
# ────────────────────────────────────────────────────────────

async def _conversation_internal(request_body: dict, request_headers: dict):
    """Core conversation logic shared by /conversation and /history/generate."""
    try:
        if app_settings.azure_openai.stream and not app_settings.base_settings.use_promptflow:
            result = await _stream_chat_request(request_body, request_headers)
            response = await make_response(format_as_ndjson(result))
            response.timeout = None
            response.mimetype = "application/json-lines"
            return response
        else:
            result = await _complete_chat_request(request_body, request_headers)
            return jsonify(result)
    except Exception as ex:
        logger.exception("Conversation internal error")
        status_code = getattr(ex, "status_code", 500)
        return jsonify({"error": str(ex), "code": "CHAT_ERROR"}), status_code


# ────────────────────────────────────────────────────────────
# API ROUTES
# ────────────────────────────────────────────────────────────

@bp.route("/conversation", methods=["POST"])
async def conversation():
    """
    Chat completions endpoint.

    Accepts the same JSON body as the OpenAI ``chat/completions`` API.
    """
    if not request.is_json:
        return jsonify({"error": "Request must be JSON", "code": "INVALID_CONTENT_TYPE"}), 415

    request_json = await request.get_json()
    return await _conversation_internal(request_json, request.headers)


# ────────────────────────────────────────────────────────────
# EOAgriTool Domain Endpoints
# ────────────────────────────────────────────────────────────

@bp.route("/sustainability_goal", methods=["POST"])
async def set_sustainability_goal():
    """
    Set the user's sustainability goal.

    Request JSON:  { "choice": "reduce_carbon_footprint" }
    Response JSON: { "message": "...", "goal": "..." }
    """
    try:
        request_json = await request.get_json()
        if not request_json:
            return jsonify({"error": "JSON body required", "code": "BAD_REQUEST"}), 400

        choice = request_json.get("choice")
        if not choice:
            return jsonify({"error": "'choice' is required", "code": "BAD_REQUEST"}), 400

        if choice not in SUSTAINABILITY_GOALS:
            return jsonify({
                "error": f"Invalid goal '{choice}'. Must be one of: {sorted(SUSTAINABILITY_GOALS)}",
                "code": "INVALID_GOAL",
            }), 400

        # Persist to CosmosDB if available
        await current_app.cosmos_db_ready.wait()
        if current_app.cosmos_conversation_client:
            try:
                user_id = get_authenticated_user_details(request_headers=request.headers)[
                    "user_principal_id"
                ]
                await current_app.cosmos_conversation_client.create_message(
                    uuid=str(uuid.uuid4()),
                    user_id=user_id,
                    input_message={"type": "sustainability_goal", "choice": choice},
                )
            except Exception:
                logger.warning("Failed to persist sustainability goal to CosmosDB", exc_info=True)

        return jsonify({"message": f"Sustainability goal '{choice}' set successfully.", "goal": choice}), 200

    except Exception:
        logger.exception("Error in /sustainability_goal")
        return jsonify({"error": "Internal server error", "code": "INTERNAL_ERROR"}), 500


@bp.route("/energy_bill", methods=["POST"])
async def process_energy_bill():
    """
    Parse an uploaded energy bill (base64-encoded file or raw text).

    Request JSON:  { "file_content": "<base64 or text>", "format": "pdf|text|image" }
    Response JSON: { "message": "...", "data": { total, usage_kwh, period, ... } }
    """
    try:
        request_json = await request.get_json()
        if not request_json:
            return jsonify({"error": "JSON body required", "code": "BAD_REQUEST"}), 400

        file_content = request_json.get("file_content")
        if not file_content:
            return jsonify({"error": "'file_content' is required", "code": "BAD_REQUEST"}), 400

        file_format = request_json.get("format", "text")
        bill_data = parse_energy_bill(file_content, file_format)

        return jsonify({"message": "Energy bill processed successfully.", "data": bill_data}), 200

    except Exception:
        logger.exception("Error in /energy_bill")
        return jsonify({"error": "Internal server error", "code": "INTERNAL_ERROR"}), 500


@bp.route("/recommendations", methods=["POST"])
async def get_recommendations():
    """
    Generate agronomic / sustainability recommendations from analysis data.

    Request JSON:  { "analysis": { ... }, "context": { ... } }
    Response JSON: { "recommendations": [...], "count": N }
    """
    try:
        request_json = await request.get_json()
        if not request_json:
            return jsonify({"error": "JSON body required", "code": "BAD_REQUEST"}), 400

        analysis = request_json.get("analysis")
        if not analysis:
            return jsonify({"error": "'analysis' is required", "code": "BAD_REQUEST"}), 400

        context = request_json.get("context", {})
        recs = generate_recommendations(analysis, context)

        return jsonify({"recommendations": recs, "count": len(recs)}), 200

    except Exception:
        logger.exception("Error in /recommendations")
        return jsonify({"error": "Internal server error", "code": "INTERNAL_ERROR"}), 500


@bp.route("/vtracker_data", methods=["GET"])
async def fetch_vtracker_data():
    """
    Fetch vehicle tracker data from the external API.

    Response JSON: { ...vtracker payload... }
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(VTRACKER_API_URL)
            resp.raise_for_status()
            return jsonify(resp.json()), 200
    except httpx.HTTPStatusError as exc:
        logger.error("vTracker API returned %d", exc.response.status_code)
        return jsonify({"error": f"Upstream vTracker API error: {exc.response.status_code}", "code": "UPSTREAM_ERROR"}), 502
    except Exception:
        logger.exception("Error in /vtracker_data")
        # Fallback data so the frontend doesn't break
        return jsonify({
            "vehicle_id": "UNAVAILABLE",
            "status": "offline",
            "source": "fallback",
        }), 200


# ────────────────────────────────────────────────────────────
# Conversation History API
# ────────────────────────────────────────────────────────────

@bp.route("/history/generate", methods=["POST"])
async def add_conversation():
    """Create or continue a conversation, returning an LLM response."""
    await current_app.cosmos_db_ready.wait()
    _require_cosmos()

    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    request_json = await request.get_json()
    conversation_id = request_json.get("conversation_id")

    try:
        history_metadata: dict = {}

        if not conversation_id:
            title = await _generate_title(request_json["messages"])
            conv_dict = await current_app.cosmos_conversation_client.create_conversation(
                user_id=user_id, title=title
            )
            conversation_id = conv_dict["id"]
            history_metadata["title"] = title
            history_metadata["date"] = conv_dict["createdAt"]

        messages = request_json["messages"]
        if not messages or messages[-1].get("role") != "user":
            raise ValueError("Last message must have role 'user'")

        created = await current_app.cosmos_conversation_client.create_message(
            uuid=str(uuid.uuid4()),
            conversation_id=conversation_id,
            user_id=user_id,
            input_message=messages[-1],
        )
        if created == "Conversation not found":
            raise ValueError(f"Conversation not found: {conversation_id}")

        request_body = await request.get_json()
        history_metadata["conversation_id"] = conversation_id
        request_body["history_metadata"] = history_metadata
        return await _conversation_internal(request_body, request.headers)

    except Exception:
        logger.exception("Exception in /history/generate")
        return jsonify({"error": "Internal server error", "code": "HISTORY_ERROR"}), 500


@bp.route("/history/update", methods=["POST"])
async def update_conversation():
    """Persist an assistant/tool message to conversation history."""
    await current_app.cosmos_db_ready.wait()
    _require_cosmos()

    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    request_json = await request.get_json()
    conversation_id = request_json.get("conversation_id")
    if not conversation_id:
        return jsonify({"error": "'conversation_id' is required", "code": "BAD_REQUEST"}), 400

    try:
        messages = request_json["messages"]
        if not messages or messages[-1].get("role") != "assistant":
            raise ValueError("Last message must have role 'assistant'")

        # If the penultimate message is a tool message, write it first
        if len(messages) > 1 and messages[-2].get("role") == "tool":
            await current_app.cosmos_conversation_client.create_message(
                uuid=str(uuid.uuid4()),
                conversation_id=conversation_id,
                user_id=user_id,
                input_message=messages[-2],
            )

        await current_app.cosmos_conversation_client.create_message(
            uuid=messages[-1]["id"],
            conversation_id=conversation_id,
            user_id=user_id,
            input_message=messages[-1],
        )

        return jsonify({"success": True}), 200

    except Exception:
        logger.exception("Exception in /history/update")
        return jsonify({"error": "Internal server error", "code": "HISTORY_ERROR"}), 500


@bp.route("/history/message_feedback", methods=["POST"])
async def update_message_feedback():
    """Update feedback (thumbs up/down) on a message."""
    await current_app.cosmos_db_ready.wait()
    _require_cosmos()

    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    request_json = await request.get_json()
    message_id = request_json.get("message_id")
    message_feedback = request_json.get("message_feedback")

    if not message_id:
        return jsonify({"error": "'message_id' is required", "code": "BAD_REQUEST"}), 400
    if not message_feedback:
        return jsonify({"error": "'message_feedback' is required", "code": "BAD_REQUEST"}), 400

    try:
        updated = await current_app.cosmos_conversation_client.update_message_feedback(
            user_id, message_id, message_feedback
        )
        if not updated:
            return jsonify({
                "error": f"Message {message_id} not found or access denied",
                "code": "NOT_FOUND",
            }), 404

        return jsonify({
            "message": f"Feedback '{message_feedback}' recorded for message {message_id}",
            "message_id": message_id,
        }), 200

    except Exception:
        logger.exception("Exception in /history/message_feedback")
        return jsonify({"error": "Internal server error", "code": "HISTORY_ERROR"}), 500


@bp.route("/history/delete", methods=["DELETE"])
async def delete_conversation():
    """Delete a conversation and all its messages."""
    await current_app.cosmos_db_ready.wait()
    _require_cosmos()

    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    request_json = await request.get_json()
    conversation_id = request_json.get("conversation_id")
    if not conversation_id:
        return jsonify({"error": "'conversation_id' is required", "code": "BAD_REQUEST"}), 400

    try:
        await current_app.cosmos_conversation_client.delete_messages(conversation_id, user_id)
        await current_app.cosmos_conversation_client.delete_conversation(user_id, conversation_id)
        return jsonify({
            "message": "Conversation and messages deleted",
            "conversation_id": conversation_id,
        }), 200
    except Exception:
        logger.exception("Exception in /history/delete")
        return jsonify({"error": "Internal server error", "code": "HISTORY_ERROR"}), 500


@bp.route("/history/list", methods=["GET"])
async def list_conversations():
    """List conversation summaries for the authenticated user."""
    await current_app.cosmos_db_ready.wait()
    _require_cosmos()

    offset = request.args.get("offset", 0, type=int)
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    try:
        conversations = await current_app.cosmos_conversation_client.get_conversations(
            user_id, offset=offset, limit=25
        )
        if not isinstance(conversations, list):
            return jsonify({"error": f"No conversations found for user", "code": "NOT_FOUND"}), 404

        return jsonify(conversations), 200
    except Exception:
        logger.exception("Exception in /history/list")
        return jsonify({"error": "Internal server error", "code": "HISTORY_ERROR"}), 500


@bp.route("/history/read", methods=["POST"])
async def get_conversation():
    """Read a conversation and its messages."""
    await current_app.cosmos_db_ready.wait()
    _require_cosmos()

    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    request_json = await request.get_json()
    conversation_id = request_json.get("conversation_id")
    if not conversation_id:
        return jsonify({"error": "'conversation_id' is required", "code": "BAD_REQUEST"}), 400

    try:
        conversation = await current_app.cosmos_conversation_client.get_conversation(
            user_id, conversation_id
        )
        if not conversation:
            return jsonify({
                "error": f"Conversation {conversation_id} not found or access denied",
                "code": "NOT_FOUND",
            }), 404

        conversation_messages = await current_app.cosmos_conversation_client.get_messages(
            user_id, conversation_id
        )

        messages = [
            {
                "id": msg["id"],
                "role": msg["role"],
                "content": msg["content"],
                "createdAt": msg["createdAt"],
                "feedback": msg.get("feedback"),
            }
            for msg in conversation_messages
        ]

        return jsonify({"conversation_id": conversation_id, "messages": messages}), 200

    except Exception:
        logger.exception("Exception in /history/read")
        return jsonify({"error": "Internal server error", "code": "HISTORY_ERROR"}), 500


@bp.route("/history/rename", methods=["POST"])
async def rename_conversation():
    """Rename a conversation."""
    await current_app.cosmos_db_ready.wait()
    _require_cosmos()

    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    request_json = await request.get_json()
    conversation_id = request_json.get("conversation_id")
    title = request_json.get("title")

    if not conversation_id:
        return jsonify({"error": "'conversation_id' is required", "code": "BAD_REQUEST"}), 400
    if not title:
        return jsonify({"error": "'title' is required", "code": "BAD_REQUEST"}), 400

    try:
        conversation = await current_app.cosmos_conversation_client.get_conversation(
            user_id, conversation_id
        )
        if not conversation:
            return jsonify({
                "error": f"Conversation {conversation_id} not found or access denied",
                "code": "NOT_FOUND",
            }), 404

        conversation["title"] = title
        updated = await current_app.cosmos_conversation_client.upsert_conversation(conversation)
        return jsonify(updated), 200

    except Exception:
        logger.exception("Exception in /history/rename")
        return jsonify({"error": "Internal server error", "code": "HISTORY_ERROR"}), 500


@bp.route("/history/delete_all", methods=["DELETE"])
async def delete_all_conversations():
    """Delete all conversations for the authenticated user."""
    await current_app.cosmos_db_ready.wait()
    _require_cosmos()

    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    try:
        conversations = await current_app.cosmos_conversation_client.get_conversations(
            user_id, offset=0, limit=None
        )
        if not conversations:
            return jsonify({"error": "No conversations found for user", "code": "NOT_FOUND"}), 404

        for conv in conversations:
            await current_app.cosmos_conversation_client.delete_messages(conv["id"], user_id)
            await current_app.cosmos_conversation_client.delete_conversation(user_id, conv["id"])

        return jsonify({"message": f"All conversations deleted for user"}), 200

    except Exception:
        logger.exception("Exception in /history/delete_all")
        return jsonify({"error": "Internal server error", "code": "HISTORY_ERROR"}), 500


@bp.route("/history/clear", methods=["POST"])
async def clear_messages():
    """Delete all messages within a conversation (keeps the conversation shell)."""
    await current_app.cosmos_db_ready.wait()
    _require_cosmos()

    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    request_json = await request.get_json()
    conversation_id = request_json.get("conversation_id")
    if not conversation_id:
        return jsonify({"error": "'conversation_id' is required", "code": "BAD_REQUEST"}), 400

    try:
        await current_app.cosmos_conversation_client.delete_messages(conversation_id, user_id)
        return jsonify({
            "message": "Messages cleared",
            "conversation_id": conversation_id,
        }), 200
    except Exception:
        logger.exception("Exception in /history/clear")
        return jsonify({"error": "Internal server error", "code": "HISTORY_ERROR"}), 500


@bp.route("/history/ensure", methods=["GET"])
async def ensure_cosmos():
    """Verify CosmosDB connectivity and configuration."""
    await current_app.cosmos_db_ready.wait()

    if not app_settings.chat_history:
        return jsonify({"error": "CosmosDB is not configured", "code": "NOT_CONFIGURED"}), 404

    try:
        success, err = await current_app.cosmos_conversation_client.ensure()
        if not current_app.cosmos_conversation_client or not success:
            return jsonify({"error": err or "CosmosDB is not working", "code": "DB_ERROR"}), (
                401 if "Invalid credentials" in str(err) else 422 if err else 500
            )

        return jsonify({"message": "CosmosDB is configured and working"}), 200

    except Exception as e:
        msg = str(e)
        if "Invalid credentials" in msg:
            return jsonify({"error": msg, "code": "AUTH_ERROR"}), 401
        if "Invalid CosmosDB database name" in msg:
            return jsonify({"error": f"{msg} ({app_settings.chat_history.database})", "code": "DB_ERROR"}), 422
        if "Invalid CosmosDB container name" in msg:
            return jsonify({"error": f"{msg} ({app_settings.chat_history.conversations_container})", "code": "DB_ERROR"}), 422
        return jsonify({"error": "CosmosDB is not working", "code": "DB_ERROR"}), 500


# ────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────

def _require_cosmos():
    """Abort if CosmosDB is not available."""
    if not current_app.cosmos_conversation_client:
        current_app.cosmos_db_ready.set()  # ensure no deadlock
        # Quart doesn't have abort with JSON easily; raise and let handler catch
        raise _CosmosNotAvailableError("CosmosDB is not configured or unavailable")


class _CosmosNotAvailableError(Exception):
    """Raised when CosmosDB is required but not available."""
    status_code = 503


async def _generate_title(conversation_messages: list[dict]) -> str:
    """Generate a short title for a new conversation using the LLM."""
    title_prompt = (
        "Summarize the conversation so far into a 4-word or less title. "
        "Do not use any quotation marks or punctuation. "
        "Do not include any other commentary or description."
    )

    # Truncate to avoid sending huge context to the title model
    truncated = conversation_messages[-MAX_CONVERSATION_MESSAGES_FOR_TITLE:]
    messages = [{"role": m["role"], "content": m["content"]} for m in truncated]
    messages.append({"role": "user", "content": title_prompt})

    try:
        client = current_app.azure_openai_client
        if not client:
            # Fallback: use first user message content
            return _fallback_title(conversation_messages)

        response = await client.chat.completions.create(
            model=app_settings.azure_openai.model,
            messages=messages,
            temperature=1,
            max_tokens=64,
        )
        return response.choices[0].message.content or _fallback_title(conversation_messages)

    except Exception:
        logger.exception("Title generation failed")
        return _fallback_title(conversation_messages)


def _fallback_title(conversation_messages: list[dict]) -> str:
    """Derive a title from the first user message if LLM title generation fails."""
    for m in conversation_messages:
        if m.get("role") == "user":
            content = m.get("content", "")
            # Take first 50 chars, strip newlines
            return content[:50].replace("\n", " ").strip() + ("..." if len(content) > 50 else "")
    return "New Conversation"