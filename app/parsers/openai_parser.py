from __future__ import annotations

import json
import os
from typing import Any, List, Optional, Tuple

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

    def check_connectivity(self) -> Tuple[bool, str]:
        """Verify that the OpenAI client can communicate with the API."""

        if not self.client:
            return False, "OpenAI client is not configured. Check OPENAI_API_KEY."

        try:
            models_api = getattr(self.client, "models", None)
            if models_api is None:
                raise AttributeError("models API not available on OpenAI client")

            if hasattr(models_api, "retrieve"):
                models_api.retrieve(self.model)
            elif hasattr(models_api, "list"):
                models_api.list()
            else:
                raise AttributeError("models API does not expose retrieve or list methods")
        except Exception as exc:  # pragma: no cover - depends on external service
            return False, f"OpenAI connectivity check failed: {exc}"

        return True, f"Connected to OpenAI (model '{self.model}')."

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
            text = self._coerce_text(output)
            if text:
                return text
        text = getattr(response, "output_text", None)
        text = self._coerce_text(text)
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
        text = self._coerce_text(content)
        if text:
            return text
        raise ParserError("Unable to extract text from chat completion response")

    def _coerce_text(self, value: Any) -> Optional[str]:
        """Best-effort conversion of structured SDK objects to plain text.

        The OpenAI Python SDK returns different shapes depending on the
        endpoint and version. Modern releases wrap text content in helper
        classes that expose a ``value`` attribute, while others may provide
        dictionaries or simple strings. This helper digs through the possible
        wrappers until it finds a string value that we can feed into
        ``json.loads``.
        """

        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            for item in value:
                text = self._coerce_text(item)
                if text:
                    return text
            return None
        if isinstance(value, dict):
            for key in ("value", "text", "content", "message"):
                if key in value:
                    text = self._coerce_text(value[key])
                    if text:
                        return text
            return None

        value_attr = getattr(value, "value", None)
        if isinstance(value_attr, str):
            return value_attr

        text_attr = getattr(value, "text", None)
        if text_attr is not None and text_attr is not value:
            text = self._coerce_text(text_attr)
            if text:
                return text

        content_attr = getattr(value, "content", None)
        if content_attr is not None and content_attr is not value:
            text = self._coerce_text(content_attr)
            if text:
                return text

        if hasattr(value, "to_dict"):
            try:
                data = value.to_dict()
            except Exception:  # pragma: no cover - defensive
                data = None
            if isinstance(data, dict):
                text = self._coerce_text(data)
                if text:
                    return text

        return None
