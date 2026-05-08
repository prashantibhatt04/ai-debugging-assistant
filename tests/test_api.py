import pytest
import json
from unittest.mock import MagicMock


FAKE_DEBUG_RESPONSE = {
    "language": "Python",
    "primary_issue": {
        "error_explanation": "NameError occurs when a variable is referenced before assignment.",
        "root_cause": "Variable 'x' is used before being defined.",
        "fix": "Define 'x' before using it.",
        "severity": "high",
    },
    "additional_issues": [
        {
            "issue": "Missing type hints",
            "explanation": "No type annotations are present on the function.",
            "fix": "Add type hints to function signatures.",
            "severity": "low",
        }
    ],
    "confidence_score": "0.95",
}

FAKE_HISTORY = [
    {
        "code": "x = undefined_var",
        "error": "NameError: name 'undefined_var' is not defined",
        "fingerprint": "abc123",
        "result": {
            "language": "Python",
            "primary_issue": {
                "error_explanation": "NameError explanation",
                "root_cause": "Undefined variable",
                "fix": "Define the variable first",
                "severity": "high",
            },
            "additional_issues": [],
            "confidence_score": "0.9",
        },
        "timestamp": "2024-01-01T00:00:00",
    }
]


def make_mock_openai_response(content: str) -> MagicMock:
    mock_response = MagicMock()
    mock_response.choices[0].message.content = content
    return mock_response


class TestHomeEndpoint:
    async def test_home_returns_200(self, client):
        response = await client.get("/")
        assert response.status_code == 200

    async def test_home_returns_expected_message(self, client):
        response = await client.get("/")
        assert response.json() == {"message": "AI Debugger Backend is running"}

    async def test_home_response_is_json(self, client):
        response = await client.get("/")
        assert "application/json" in response.headers["content-type"]


class TestDebugEndpoint:
    def _mock_openai(self, mocker):
        return mocker.patch(
            "main.client.chat.completions.create",
            return_value=make_mock_openai_response(json.dumps(FAKE_DEBUG_RESPONSE)),
        )

    async def test_debug_returns_200_with_valid_input(self, client, mocker):
        self._mock_openai(mocker)
        mocker.patch("main.write_history")
        mocker.patch("main.read_history", return_value=[])

        response = await client.post(
            "/debug", json={"code": "print('hello')", "error": "NameError"}
        )
        assert response.status_code == 200

    async def test_debug_response_matches_debug_response_schema(self, client, mocker):
        self._mock_openai(mocker)
        mocker.patch("main.write_history")
        mocker.patch("main.read_history", return_value=[])

        response = await client.post(
            "/debug", json={"code": "x = 1", "error": "TypeError"}
        )
        data = response.json()
        assert "language" in data
        assert "primary_issue" in data
        assert "additional_issues" in data
        assert "confidence_score" in data
        primary = data["primary_issue"]
        assert all(k in primary for k in ("error_explanation", "root_cause", "fix", "severity"))

    async def test_debug_calls_openai_exactly_once(self, client, mocker):
        mock_create = self._mock_openai(mocker)
        mocker.patch("main.write_history")
        mocker.patch("main.read_history", return_value=[])

        await client.post("/debug", json={"code": "print('hello')", "error": "SyntaxError"})
        mock_create.assert_called_once()

    async def test_debug_returns_422_when_code_is_empty(self, client):
        response = await client.post("/debug", json={"code": "", "error": "SyntaxError"})
        assert response.status_code == 422

    async def test_debug_returns_422_when_code_is_whitespace_only(self, client):
        response = await client.post("/debug", json={"code": "   ", "error": "SyntaxError"})
        assert response.status_code == 422

    async def test_debug_returns_422_when_error_is_empty(self, client):
        response = await client.post(
            "/debug", json={"code": "print('hello')", "error": ""}
        )
        assert response.status_code == 422

    async def test_debug_returns_422_when_error_is_whitespace_only(self, client):
        response = await client.post(
            "/debug", json={"code": "print('hello')", "error": "   "}
        )
        assert response.status_code == 422

    async def test_debug_returns_422_when_code_exceeds_5000_characters(self, client):
        response = await client.post(
            "/debug", json={"code": "x" * 5001, "error": "SyntaxError"}
        )
        assert response.status_code == 422

    async def test_debug_accepts_code_at_exactly_5000_characters(self, client, mocker):
        self._mock_openai(mocker)
        mocker.patch("main.write_history")
        mocker.patch("main.read_history", return_value=[])

        response = await client.post(
            "/debug", json={"code": "x" * 5000, "error": "SyntaxError"}
        )
        assert response.status_code == 200


class TestGetHistoryEndpoint:
    async def test_history_returns_200(self, client, mocker):
        mocker.patch("main.read_history", return_value=FAKE_HISTORY)
        response = await client.get("/history")
        assert response.status_code == 200

    async def test_history_returns_a_list(self, client, mocker):
        mocker.patch("main.read_history", return_value=FAKE_HISTORY)
        response = await client.get("/history")
        assert isinstance(response.json(), list)

    async def test_history_items_contain_required_fields(self, client, mocker):
        mocker.patch("main.read_history", return_value=FAKE_HISTORY)
        response = await client.get("/history")
        item = response.json()[0]
        assert "code" in item
        assert "error" in item
        assert "result" in item

    async def test_history_returns_422_when_limit_is_zero(self, client):
        response = await client.get("/history?limit=0")
        assert response.status_code == 422

    async def test_history_returns_422_when_limit_exceeds_100(self, client):
        response = await client.get("/history?limit=101")
        assert response.status_code == 422

    async def test_history_returns_422_when_offset_is_negative(self, client):
        response = await client.get("/history?offset=-1")
        assert response.status_code == 422

    async def test_history_respects_limit_parameter(self, client, mocker):
        mocker.patch("main.read_history", return_value=FAKE_HISTORY * 10)
        response = await client.get("/history?limit=3")
        assert len(response.json()) == 3

    async def test_history_returns_empty_list_when_no_history_exists(self, client, mocker):
        mocker.patch("main.read_history", return_value=[])
        response = await client.get("/history")
        assert response.json() == []


class TestDeleteHistoryEndpoint:
    async def test_delete_history_returns_200_with_confirm_true(self, client, mocker):
        mocker.patch("main.write_history")
        response = await client.delete("/history?confirm=true")
        assert response.status_code == 200

    async def test_delete_history_returns_success_message(self, client, mocker):
        mocker.patch("main.write_history")
        response = await client.delete("/history?confirm=true")
        assert response.json() == {"message": "History cleared successfully"}

    async def test_delete_history_writes_empty_list_to_storage(self, client, mocker):
        mock_write = mocker.patch("main.write_history")
        await client.delete("/history?confirm=true")
        mock_write.assert_called_once_with([])

    async def test_delete_history_returns_400_without_confirm_param(self, client):
        response = await client.delete("/history")
        assert response.status_code == 400

    async def test_delete_history_returns_400_when_confirm_is_false(self, client):
        response = await client.delete("/history?confirm=false")
        assert response.status_code == 400

    async def test_delete_history_error_detail_mentions_confirm(self, client):
        response = await client.delete("/history")
        assert "confirm" in response.json()["detail"].lower()


class TestAnalyticsEndpoint:
    async def test_analytics_returns_200(self, client, mocker):
        mocker.patch("main.read_history", return_value=[])
        response = await client.get("/analytics")
        assert response.status_code == 200

    async def test_analytics_returns_required_top_level_fields(self, client, mocker):
        mocker.patch("main.read_history", return_value=[])
        response = await client.get("/analytics")
        data = response.json()
        assert "total_requests" in data
        assert "severity_distribution" in data
        assert "top_recurring_errors" in data

    async def test_analytics_total_requests_matches_history_length(self, client, mocker):
        mocker.patch("main.read_history", return_value=FAKE_HISTORY)
        response = await client.get("/analytics")
        assert response.json()["total_requests"] == len(FAKE_HISTORY)

    async def test_analytics_severity_distribution_counts_correctly(self, client, mocker):
        mocker.patch("main.read_history", return_value=FAKE_HISTORY)
        response = await client.get("/analytics")
        dist = response.json()["severity_distribution"]
        assert dist["high"] == 1
        assert dist["medium"] == 0
        assert dist["low"] == 0

    async def test_analytics_returns_zero_totals_with_empty_history(self, client, mocker):
        mocker.patch("main.read_history", return_value=[])
        response = await client.get("/analytics")
        data = response.json()
        assert data["total_requests"] == 0
        assert data["top_recurring_errors"] == []

    async def test_analytics_top_recurring_errors_is_a_list(self, client, mocker):
        mocker.patch("main.read_history", return_value=FAKE_HISTORY)
        response = await client.get("/analytics")
        assert isinstance(response.json()["top_recurring_errors"], list)


class TestInsightsEndpoint:
    def _mock_openai(self, mocker, content="Reduce reliance on global variables."):
        return mocker.patch(
            "main.client.chat.completions.create",
            return_value=make_mock_openai_response(content),
        )

    async def test_insights_returns_200(self, client, mocker):
        mocker.patch("main.read_history", return_value=[])
        self._mock_openai(mocker)
        response = await client.get("/insights")
        assert response.status_code == 200

    async def test_insights_returns_analytics_and_insights_fields(self, client, mocker):
        mocker.patch("main.read_history", return_value=[])
        self._mock_openai(mocker)
        response = await client.get("/insights")
        data = response.json()
        assert "analytics" in data
        assert "insights" in data

    async def test_insights_analytics_contains_required_keys(self, client, mocker):
        mocker.patch("main.read_history", return_value=FAKE_HISTORY)
        self._mock_openai(mocker)
        response = await client.get("/insights")
        analytics = response.json()["analytics"]
        assert "total_requests" in analytics
        assert "severity_distribution" in analytics
        assert "top_recurring_errors" in analytics

    async def test_insights_field_contains_openai_response_text(self, client, mocker):
        mocker.patch("main.read_history", return_value=[])
        self._mock_openai(mocker, content="Focus on undefined variable patterns.")
        response = await client.get("/insights")
        assert response.json()["insights"] == "Focus on undefined variable patterns."

    async def test_insights_calls_openai_exactly_once(self, client, mocker):
        mocker.patch("main.read_history", return_value=[])
        mock_create = self._mock_openai(mocker)
        await client.get("/insights")
        mock_create.assert_called_once()

    async def test_insights_returns_500_when_openai_raises_exception(self, client, mocker):
        mocker.patch("main.read_history", return_value=[])
        mocker.patch(
            "main.client.chat.completions.create",
            side_effect=Exception("OpenAI unavailable"),
        )
        response = await client.get("/insights")
        assert response.status_code == 500
