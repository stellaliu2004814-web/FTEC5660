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

    Uses deepseek-v4-flash-vision-exp as the vision backbone model.
    Returns the raw LLM (not wrapped with structured output) because the
    model's thinking mode is incompatible with tool_choice / function
    calling. Instead, we instruct the model via prompt to return JSON,
    which we parse in answer_queries().
    """
    from langchain_deepseek import ChatDeepSeek

    llm = ChatDeepSeek(
        model="deepseek-v4-flash-vision-exp",
        temperature=0,
        max_retries=2,
    )
    return llm


def answer_queries(chain: Any, images: list[Path]) -> dict[str, Any]:
    """Run the chain on all receipt images and return one response per query.

    For each receipt image we build a multimodal message (system prompt + text
    instruction + base64 image) and run them all in parallel with chain.batch().
    The model is prompted to return JSON with three fields, which we parse and
    aggregate:

        Query 1 (total spent)            = sum of amount_paid_after_rounding
        Query 2 (without discount)       = sum of (subtotal + discount_total)
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    system_prompt = (
        "You are an expert at reading Hong Kong supermarket receipts (e.g. "
        "from Fusion, PARKnSHOP, Wellcome, AEON). You must examine every "
        "single line on the receipt carefully.\n\n"
        "You MUST respond with ONLY a JSON object in this exact format, "
        "with no other text before or after:\n"
        '{"amount_paid_after_rounding": <number>, "subtotal": <number>, '
        '"discount_total": <number>, "discount_lines": [<list of strings>]}\n\n'
        "Field definitions:\n"
        "- amount_paid_after_rounding: The final amount actually paid AFTER "
        "rounding. Look for the payment method line (OCTOPUS, CASH, VISA, "
        "ALIPAY, etc.).\n"
        "- subtotal: The SUBTOTAL line (after all discounts, before rounding).\n"
        "- discount_total: The sum of ALL discounts, promotions, coupons, "
        "member offers, app discounts, packaging-damage reductions, and "
        "percentage-off lines, as a POSITIVE number.\n"
        "- discount_lines: List EVERY discount/promotion/coupon line you see "
        "on the receipt, including its description and amount (e.g. "
        "\"5% OFF -5.39\", \"MEMBER OFFER -2.00\", \"COUPON -1.00\").\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. Read EVERY line on the receipt from top to bottom. Do not skip "
        "any line.\n"
        "2. Any line with a minus sign (-) or described as OFF, DISCOUNT, "
        "PROMOTION, COUPON, MEMBER, SAVING, SAVE, or similar is a discount.\n"
        "3. ROUNDING is NOT a discount. It is a tiny adjustment (usually "
        "HK$0.01-HK$0.09) to round the total. Exclude it from discount_total.\n"
        "4. List ALL discount lines in discount_lines, then sum their amounts "
        "for discount_total. Double-check your arithmetic.\n"
        "5. Verify: subtotal + discount_total should equal the sum of all "
        "original item prices (before any discounts).\n\n"
        "Return ONLY the JSON. No markdown, no explanation."
    )

    human_prompt = (
        "Examine this Hong Kong supermarket receipt image and extract the "
        "three monetary values. Return ONLY the JSON object."
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
    raw_results = chain.batch(messages_list)

    # Parse JSON from each response and aggregate
    total_paid = 0.0
    total_without_discount = 0.0

    for i, result in enumerate(raw_results):
        text = response_text(result)
        # Strip markdown code fences if present
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        try:
            data = json.loads(clean)
            total_paid += float(data["amount_paid_after_rounding"])
            total_without_discount += float(data["subtotal"]) + float(
                data["discount_total"]
            )
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            # Fallback: try to extract the first JSON object via regex
            match = re.search(r"\{[^}]+\}", text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                    total_paid += float(data["amount_paid_after_rounding"])
                    total_without_discount += float(data["subtotal"]) + float(
                        data["discount_total"]
                    )
                except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                    pass  # skip unparseable receipt

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
