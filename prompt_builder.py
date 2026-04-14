def build_debug_prompt(code: str, error: str, history_context: str) -> str:
    return f"""
You are a senior software engineer debugging a legacy codebase.

Context:
- The code may be poorly written, incomplete, or inconsistent
- Focus on practical debugging, not theory
- Assume this is production code with real users impacted
- Consider prior recurring issues when relevant, but do not force a match

INPUT:

Code:
{code}

Error:
{error}

Relevant Previous Debug History:
{history_context}

TASK:

1. Identify the programming language
2. Explain the primary issue clearly
3. Identify possible root causes
4. Suggest a fix (practical, not idealistic)
5. Provide refactored code if possible
6. Mention any additional issues you notice
7. Use previous history only if it genuinely helps

OUTPUT FORMAT (STRICT JSON):

{{
  "language": "...",
  "primary_issue": {{
    "error_explanation": "...",
    "root_cause": "...",
    "fix": "...",
    "severity": "low | medium | high"
  }},
  "additional_issues": [
    {{
      "issue": "...",
      "explanation": "...",
      "fix": "...",
      "severity": "low | medium"
    }}
  ],
  "confidence_score": "0-100%"
}}
"""