from fastapi import FastAPI, HTTPException, Query, status, Request
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv
import os
from openai import OpenAI
import json
from datetime import datetime
from typing import List, Optional
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
import logging
from config import settings, IS_PRODUCTION
from prompt_builder import build_debug_prompt
from utils import generate_error_fingerprint

if settings.ENV == "development":
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.WARNING)

logger = logging.getLogger(__name__)

# load env variables
load_dotenv()

# initialize app
app = FastAPI()

@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"message": "Too many requests. Please try again later."}
    )

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# request body structure
class DebugRequest(BaseModel):
    code: str
    error: str

    @field_validator("code")
    def validate_code(cls, value):
        if not value.strip():
            raise ValueError("Code cannot be empty")
        if len(value) > 5000:
            raise ValueError("Code is too long (max 5000 characters)")
        return value

    @field_validator("error")
    def validate_error(cls, value):
        if not value.strip():
            raise ValueError("Error message cannot be empty")
        return value

class Issue(BaseModel):
    issue: str
    explanation: str
    fix: str
    severity: str

class PrimaryIssue(BaseModel):
    error_explanation: str
    root_cause: str
    fix: str
    severity: str

class DebugResponse(BaseModel):
    language: str
    primary_issue: PrimaryIssue
    additional_issues: list[Issue]
    confidence_score: str

class HistoryItem(BaseModel):
    code: str
    error: str
    result: dict
    timestamp: Optional[str] = None

def read_history():
    try:
        with open(settings.HISTORY_FILE, "r") as file:
            return json.load(file)
    except:
        return []

def write_history(data):
    with open(settings.HISTORY_FILE, "w") as file:
        json.dump(data, file, indent=2)

def get_recent_relevant_history(current_error: str, limit: int = 3):
    history = read_history()

    if not history:
        return []

    current_fingerprint = generate_error_fingerprint(current_error)

    # Step 1: Exact matches
    exact_matches = [
        item for item in history
        if item.get("fingerprint") == current_fingerprint
    ]

    if exact_matches:
        return exact_matches[:limit]

    # Step 2: fallback to keyword matching
    current_error_words = set(current_error.lower().split())
    matched_items = []

    for item in history:
        previous_error = item.get("error", "")
        previous_words = set(previous_error.lower().split())

        if current_error_words.intersection(previous_words):
            matched_items.append(item)

        if len(matched_items) >= limit:
            break

    return matched_items[:limit] if matched_items else history[:limit]

def format_history_context(history_items: list) -> str:
    """
    Convert history items into compact text that can be added
    to the debugging prompt.
    """
    if not history_items:
        return "No similar previous debug history found."

    formatted_items = []

    for index, item in enumerate(history_items, start=1):
        error_text = item.get("error", "Unknown error")
        result = item.get("result", {})
        primary_issue = result.get("primary_issue", {})
        root_cause = primary_issue.get("root_cause", "Unknown root cause")
        fix = primary_issue.get("fix", "No suggested fix recorded")

        formatted_items.append(
            f"""
Previous Case {index}:
Error: {error_text}
Likely Root Cause: {root_cause}
Suggested Fix: {fix}
""".strip()
        )

    return "\n\n".join(formatted_items)

@app.get("/")
def home():
    return {"message": "AI Debugger Backend is running"}

@app.post("/debug", response_model=DebugResponse)
@limiter.limit(settings.RATE_LIMIT)
def debug_code(request_data: DebugRequest, request: Request = None):
   
    relevant_history = get_recent_relevant_history(request_data.error)
    logger.info(f"Found {len(relevant_history)} relevant history items for context enrichment")
    history_context = format_history_context(relevant_history)
    prompt = build_debug_prompt(
    code=request_data.code,
    error=request_data.error,
    history_context=history_context
    )

    logger.info("Sending debug request to OpenAI")
    
    response = client.chat.completions.create(
    model=settings.MODEL_NAME,
    messages=[
        {"role": "system", "content": "You are a senior debugging assistant."},
        {"role": "user", "content": prompt}
    ],
    temperature=0.2
    )

    output = response.choices[0].message.content

    logger.info("Received response from OpenAI")

    # CLEAN the output
    output = output.replace("```json", "").replace("```", "").strip()

    logger.info(f"CLEANED OUTPUT: {output}")

    logger.info(f"RAW OUTPUT: {output}")

# Step 1: Parse JSON
    try:
        parsed_output = json.loads(output)
        logger.info("JSON parsed successfully")
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing failed: {str(e)}")

        if IS_PRODUCTION:
            raise HTTPException(
                status_code=500,
                detail="Internal server error"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Parsing error: {str(e)}"
            )

# Step 2: Save to history
    logger.info("Saving to history...")

    error_fingerprint = generate_error_fingerprint(request_data.error)
    history = read_history()

    history.append({
    "code": request_data.code,
    "error": request_data.error,
    "fingerprint": error_fingerprint,
    "result": parsed_output,
    "timestamp": datetime.utcnow().isoformat()
})

    write_history(history)

# Step 3: Return response
    return parsed_output

@app.get("/history", response_model=list[HistoryItem])
def get_history(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    history = read_history()

    for item in history:
        if "timestamp" not in item:
            item["timestamp"] = ""

    history = sorted(history, key=lambda x: x.get("timestamp", ""), reverse=True)

    # Apply pagination
    paginated_history = history[offset: offset + limit]

    return paginated_history

@app.delete("/history")
def clear_history(confirm: bool = Query(False)):
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set confirm=true to delete all history"
        )

    write_history([])

    return {"message": "History cleared successfully"}

@app.get("/analytics")
def get_analytics():
    return generate_analytics()

def generate_analytics():
    history = read_history()

    total_requests = len(history)

    fingerprint_count = {}
    severity_count = {"low": 0, "medium": 0, "high": 0}

    for item in history:
        # Count recurring errors (fingerprints)
        fp = item.get("fingerprint")
        if fp:
            fingerprint_count[fp] = fingerprint_count.get(fp, 0) + 1

        # Count severity
        result = item.get("result", {})
        primary = result.get("primary_issue", {})
        severity = primary.get("severity", "low").lower()

        if severity in severity_count:
            severity_count[severity] += 1

    # Top recurring errors
    top_errors = sorted(
        fingerprint_count.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]

    return {
        "total_requests": total_requests,
        "severity_distribution": severity_count,
        "top_recurring_errors": top_errors
    }

def build_insights_prompt(analytics_data: dict) -> str:
    return f"""
You are a senior software engineer analyzing debugging trends in a legacy codebase.

Here is analytics data from a debugging system:

{analytics_data}

TASK:
- Identify patterns in errors
- Highlight the most critical issues
- Suggest possible root causes at system level
- Suggest improvements for engineering teams

Keep response concise and practical.

Output as plain text (not JSON).
"""

@app.get("/insights")
def get_insights():
    analytics_data = generate_analytics()

    prompt = build_insights_prompt(analytics_data)

    try:
        response = client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are an engineering analytics expert."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        insights = response.choices[0].message.content

        return {
            "analytics": analytics_data,
            "insights": insights
        }

    except Exception as e:
        logger.error(f"Insights generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate insights")