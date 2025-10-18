from __future__ import annotations

import json
import os
from typing import Any, List, Optional

from app.models.transaction import Transaction

from .base import BaseParser, ParserError

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except Exception:  # pragma: no cover - fallback when package missing
    OpenAI = None


class OpenAIParser(BaseParser):
    name = "openai"

    def __init__(self, client: Optional[OpenAI] = None, model: Optional[str] = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        if client is not None:
            self.client = client
        elif api_key and OpenAI is not None:
            self.client = OpenAI(api_key=api_key)
        else:
            self.client = None

    def is_available(self) -> bool:
        return self.client is not None

    def parse(self, pdf_bytes: bytes) -> List[Transaction]:
        if not self.client:
            raise ParserError("OpenAI client is not configured")

        from app.utils.pdf import extract_text_from_pdf

        text = extract_text_from_pdf(pdf_bytes)
        prompt = (
            "You will receive the raw text of a credit card statement. "
            "Return a JSON array with objects that contain the following keys: "
            "trans_date, post_date, reference_number, description, amount. "
            "Only include rows that represent paid transactions (they contain an amount). "
            "Amounts should be numbers where charges are negative (money spent) and payments are positive."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ]
        raw = self._request_json(messages)

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ParserError(f"Failed to decode JSON from OpenAI: {exc}") from exc

        transactions_data = payload.get("transactions") or payload
        if not isinstance(transactions_data, list):
            raise ParserError("OpenAI response does not contain a list of transactions")

        transactions: List[Transaction] = []
        for item in transactions_data:
            try:
                transactions.append(Transaction(**item))
            except Exception as exc:
                raise ParserError(f"Invalid transaction payload: {exc}") from exc
        if not transactions:
            raise ParserError("OpenAI did not return any transactions")
        return transactions

    # --- private helpers -------------------------------------------------

    def _request_json(self, messages: List[dict[str, str]]) -> str:
        """Request JSON text from the OpenAI client.

        The OpenAI SDK has evolved quickly and different versions expose
        different APIs. Newer releases provide ``client.responses.create`` with
        ``response_format`` support, while older ones only support the
        ChatCompletions endpoint. This helper tries the most structured option
        first and gracefully falls back to the older behaviours so the parser
        keeps working regardless of the installed SDK version.
        """

        # Prefer the modern responses API when available.
        responses_api = getattr(self.client, "responses", None)
        if responses_api:
            try:
                response = responses_api.create(
                    model=self.model,
                    input=messages,
                    response_format={"type": "json_object"},
                )
            except TypeError as exc:
                # Older SDKs don't recognise the response_format argument.
                if "response_format" not in str(exc):
                    raise
                response = responses_api.create(model=self.model, input=messages)
            return self._extract_responses_text(response)

        # Fallback: use chat completions endpoint when the responses API isn't
        # available. We again try ``response_format`` first for newer versions
        # and retry without it when unsupported.
        chat = getattr(getattr(self.client, "chat", None), "completions", None)
        if chat:
            kwargs = {"model": self.model, "messages": messages}
            try:
                response = chat.create(
                    **kwargs, response_format={"type": "json_object"}
                )
            except TypeError as exc:
                if "response_format" not in str(exc):
                    raise
                response = chat.create(**kwargs)
            return self._extract_chat_text(response)

        raise ParserError("OpenAI client does not support responses or chat completions")

    def _extract_responses_text(self, response: Any) -> str:
        """Extract the text payload from a responses API result."""

        output = getattr(response, "output", None)
        if output:
            first = output[0]
            content = getattr(first, "content", None)
            if content:
                text = getattr(content[0], "text", None)
                if text:
                    return text
        text = getattr(response, "output_text", None)
        if text:
            return text
        raise ParserError("Unexpected OpenAI responses payload")

    def _extract_chat_text(self, response: Any) -> str:
        """Extract the text payload from a chat completion result."""

        choices = getattr(response, "choices", None)
        if not choices:
            raise ParserError("Chat completion did not return any choices")
        message = getattr(choices[0], "message", None)
        if not message:
            raise ParserError("Chat completion is missing message content")
        content = getattr(message, "content", None)
        if not content:
            raise ParserError("Chat completion message does not contain text")
        if isinstance(content, str):
            return content
        # Some SDK versions return a list of content parts.
        if isinstance(content, list) and content:
            text = getattr(content[0], "text", None)
            if text:
                return text
        raise ParserError("Unable to extract text from chat completion response")
