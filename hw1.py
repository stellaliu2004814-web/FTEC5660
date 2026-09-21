#!/usr/bin/env python3
"""FTEC5660 HW1 student starter: build a chain for supermarket receipts."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import mimetypes
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


QUERY_1 = "How much money did I spend in total for these bills?"
QUERY_2 = "How much would I have had to pay without the discount?"
QUERIES = (QUERY_1, QUERY_2)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
DUMMY_RESPONSE = "please design your chain to answer these two queries."


def load_env_file(path: Path = Path(".env")) -> None:
    """Load the simple KEY=VALUE entries used by this homework."""
    if not path.is_file():
        return
    import os

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def image_files(folder: Path) -> list[Path]:
    """Return supported images directly inside *folder*, sorted by filename."""
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def image_data_url(path: Path) -> str:
    """Encode a local image in the format accepted by a multimodal prompt."""
    mime_type, _ = mimetypes.guess_type(path.name)
    mime_type = mime_type or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_chain() -> Any:
    """Create and return your LangChain chain once.

    Uses deepseek-v4-flash-vision-exp as the vision backbone model with
    structured output (Pydantic) for reliable per-receipt field extraction.
    """
    from langchain_deepseek import ChatDeepSeek
    from pydantic import BaseModel, Field

    class ReceiptData(BaseModel):
        """Structured data extracted from a single supermarket receipt."""

        amount_paid_after_rounding: float = Field(
            description=(
                "The final payment amount on the receipt AFTER rounding. "
                "This is the amount actually paid via the payment method "
                "(e.g., OCTOPUS, CASH, VISA, ALIPAY). Do NOT include ROUNDING."
            )
        )
        subtotal: float = Field(
            description=(
                "The SUBTOTAL amount shown on the receipt (after all discounts "
                "have been applied, but BEFORE any rounding adjustment)."
            )
        )
        discount_total: float = Field(
            description=(
                "The sum of ALL discount/promotion/coupon/member/offer lines on "
                "the receipt, expressed as a POSITIVE number. Include every "
                "promotion, coupon, member discount, app discount, packaging "
                "damage reduction, and percentage-off line. Do NOT include the "
                "ROUNDING line here."
            )
        )

    llm = ChatDeepSeek(
        model="deepseek-v4-flash-vision-exp",
        temperature=0,
        max_retries=2,
    )

    # Wrap the LLM with structured output so each receipt returns a ReceiptData
    structured_llm = llm.with_structured_output(ReceiptData)
    return structured_llm


def answer_queries(chain: Any, images: list[Path]) -> dict[str, Any]:
    """Run the chain on all receipt images and return one response per query.

    For each receipt image we build a multimodal message (system prompt + text
    instruction + base64 image) and run them all in parallel with chain.batch().
    Then we aggregate the structured fields:

        Query 1 (total spent)            = sum of amount_paid_after_rounding
        Query 2 (without discount)       = sum of (subtotal + discount_total)
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    system_prompt = (
        "You are an expert at reading Hong Kong supermarket receipts. "
        "Carefully examine the receipt image and extract the exact monetary "
        "values requested. Pay close attention to:\n"
        "- The final payment amount (after rounding), typically shown next to "
        "  a payment method like OCTOPUS, CASH, VISA, CREDIT CARD, ALIPAY, "
        "  etc.\n"
        "- The SUBTOTAL line (after all discounts, before rounding).\n"
        "- All discount/promotion/coupon/offer lines (as positive numbers).\n"
        "Do NOT confuse rounding with discounts. Rounding is a small "
        "adjustment (usually HK$0.01-HK$0.09) to make the total a round number."
    )

    human_prompt = (
        "Extract the following three values from this Hong Kong supermarket "
        "receipt image:\n"
        "1. amount_paid_after_rounding: The final amount actually paid "
        "(after any rounding adjustment). Look for the payment method line "
        "(OCTOPUS, CASH, VISA, etc.).\n"
        "2. subtotal: The SUBTOTAL amount (after discounts, before rounding).\n"
        "3. discount_total: The sum of ALL discounts, promotions, coupons, "
        "and offers (as a positive number). Do NOT include rounding.\n\n"
        "Return ONLY the structured data. Do not include any extra text."
    )

    # Build one multimodal message per receipt image
    messages_list: list[list[Any]] = []
    for img_path in images:
        data_url = image_data_url(img_path)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=[
                    {"type": "text", "text": human_prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]
            ),
        ]
        messages_list.append(messages)

    # Batch-process all receipts in parallel
    results = chain.batch(messages_list)

    # Aggregate across all receipts
    total_paid = sum(float(r.amount_paid_after_rounding) for r in results)
    total_without_discount = sum(
        float(r.subtotal) + float(r.discount_total) for r in results
    )

    return {
        QUERY_1: f"HK${total_paid:.2f}",
        QUERY_2: f"HK${total_without_discount:.2f}",
    }


# Everything below is provided runner/scoring code. No edits are needed.

_MONEY_RE = re.compile(
    r"(?<![\w.])(?:HK\$|\$)?\s*(-?\d[\d,]*(?:\.\d+)?)(?![\w.])",
    re.IGNORECASE,
)


def response_text(value: Any) -> str:
    """Convert common LangChain response shapes to text for results.csv."""
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts).strip()
    if isinstance(content, (dict, list)):
        return json.dumps(content, ensure_ascii=False)
    return str(content).strip()


def parse_single_amount(text: str) -> Decimal | None:
    """Accept a response only when it contains exactly one numeric amount."""
    matches = _MONEY_RE.findall(text)
    if len(matches) != 1:
        return None
    try:
        return Decimal(matches[0].replace(",", "")).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def read_ground_truth(folder: Path) -> dict[str, Decimal]:
    """Read aggregate answers from the test folder."""
    path = folder / "ground_truth.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    answers = data.get("answers", data)
    return {query: Decimal(str(answers[query])).quantize(Decimal("0.01")) for query in QUERIES}


def correctness_text(response: str, expected: Decimal | None) -> str:
    """Return `correct`, or an expected/predicted mismatch explanation."""
    if expected is None:
        return "not graded: ground_truth.json is missing"
    predicted = parse_single_amount(response)
    if predicted == expected:
        return "correct"
    shown = f"HK${predicted:.2f}" if predicted is not None else repr(response)
    return f"incorrect: expected HK${expected:.2f}, predicted {shown}"


def write_results(responses: dict[str, Any], truth: dict[str, Decimal]) -> Path:
    """Write the required three-column results.csv file."""
    output = Path("results.csv")
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["query", "model_response", "correctness"])
        for query in QUERIES:
            text = response_text(responses.get(query, "<missing response>"))
            writer.writerow([query, text, correctness_text(text, truth.get(query))])
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run FTEC5660 HW1 on receipt images")
    parser.add_argument(
        "--image-folder",
        required=True,
        type=Path,
        help="folder containing supermarket receipt images",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.image_folder.is_dir():
        raise SystemExit(f"not a folder: {args.image_folder}")

    images = image_files(args.image_folder)
    if not images:
        raise SystemExit(f"no supported images found in {args.image_folder}")

    load_env_file()
    chain = build_chain()
    responses = answer_queries(chain, images)
    if not isinstance(responses, dict):
        raise TypeError("answer_queries() must return a dictionary")

    output = write_results(responses, read_ground_truth(args.image_folder))
    print(f"Processed {len(images)} receipt(s). Wrote {output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
