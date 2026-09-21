# FTEC5660 Homework 1: Receipt Chain

Build a LangChain pipeline that reads every supermarket receipt in a folder
with the vision-capable DeepSeek Flash model and answers these two questions:

1. How much money did I spend in total for these bills?
2. How much would I have had to pay without the discount?

For this homework, **amount spent** means the final payment after the receipt's
rounding line. **Without the discount** means the sum of the original positive
item prices: add back every promotion, coupon, member, app, packaging-damage,
and percentage discount, but do not add back rounding.

## Student task

Only edit the two functions in `hw1.py` that contain `### YOUR CODE HERE`:

- `build_chain()` creates your LangChain chain.
- `answer_queries()` runs the chain on the receipt images and returns one final
  response for each question.

You may use prompt chaining, routing, parallel calls, reflection, or a
combination. Your final responses should each contain one HKD amount. Do not
hard-code filenames or public answers; grading uses unseen receipt folders.

## Setup and public test

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Put your DeepSeek key after `DEEPSEEK_API_KEY=` in `.env`, then run:

```bash
python3 hw1.py --image-folder public_test
```

The program creates `results.csv` in the current directory. Its columns are
`query`, `model_response`, and `correctness`. The public answers are in
`public_test/ground_truth.json`. The starter intentionally returns the dummy
response `please design your chain to answer these two queries.` so it runs
before you add any API code.

The required model is `deepseek-v4-flash-vision-exp`, the vision-capable
DeepSeek Flash model. JPEG, PNG, GIF, and WebP inputs are accepted by the
homework runner.


## Homework 1 solution:

### Chain Design

My solution uses a two-stage LangChain pipeline:

1. **Per-receipt extraction (parallel)** — For each receipt image, a multimodal
   message (system prompt + text instruction + base64-encoded image) is sent
   to the vision-capable `deepseek-v4-flash-vision-exp` model wrapped with
   `with_structured_output(ReceiptData)`. Each call returns a Pydantic object
   with three fields:

   - `amount_paid_after_rounding` — the final payment after rounding (e.g.,
     the OCTOPUS / CASH / VISA line)
   - `subtotal` — the SUBTOTAL line (after discounts, before rounding)
   - `discount_total` — the sum of all discount / promotion / coupon / member /
     app lines (as a positive number, excluding rounding)

   All receipts are processed concurrently via `chain.batch()`.

2. **Aggregation** — The structured fields are summed across every receipt:

   - **Query 1** (total spent)            = Σ `amount_paid_after_rounding`
   - **Query 2** (without discount)       = Σ (`subtotal` + `discount_total`)

   Results are returned as a dict keyed by the exact query strings, formatted
   as `"HK$xxxx.xx"` so the grader's regex picks up exactly one numeric value.

### Chain Architecture Diagram

```
  receipt1.jpg ──┐
  receipt2.jpg ──┤  ┌──────────────────────────────┐  ┌──────────────┐
  receipt3.jpg ──┼─▶│  ChatDeepSeek(model=          │─▶│ ReceiptData   │
  ...          ──┤  │   "deepseek-v4-flash-         │  │ (Pydantic)    │
  receiptN.jpg ──┘  │   vision-exp")                │  │ - amount_paid │
                   │   .with_structured_output(...)  │  │ - subtotal    │
                   │   .batch(messages_list)        │  │ - discount    │
                   └──────────────────────────────┘  │   _total      │
                                                     └──────┬───────┘
                                                            │
                                          ┌─────────────────┘
                                          ▼
                                ┌──────────────────────────┐
                                │       Aggregation         │
                                │  Q1 = Σ amount_paid       │
                                │  Q2 = Σ (sub + discount)  │
                                └──────────┬───────────────┘
                                           ▼
                          {QUERY_1: "HK$1974.30",
                           QUERY_2: "HK$2348.20"}
```

### Solution Description

The hardest part is reliably separating *discounts* (which Query 2 must add
back) from *rounding* (which it must ignore). The system prompt explicitly
warns the model: "Do NOT confuse rounding with discounts. Rounding is a
small adjustment (usually HK$0.01–HK$0.09) to make the total a round number."
Combined with a Pydantic schema that names the fields in plain English
(`amount_paid_after_rounding`, `subtotal`, `discount_total`), the model is
nudged to read each receipt line-by-line instead of pattern-matching numbers.

`temperature=0` keeps outputs deterministic across runs, and `max_retries=2`
recovers from the occasional transient API failure. Because the schema is the
same on every receipt, the chain generalizes to unseen receipt folders —
nothing about filenames, currencies, or vendor layouts is hard-coded.

