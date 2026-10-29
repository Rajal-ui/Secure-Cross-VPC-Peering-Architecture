import hmac
import logging
import os

from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_REQUEST_BYTES", "16384"))
API_KEY = os.environ.get("RECONCILE_API_KEY", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("finance-controller")


def is_authorized() -> bool:
    if not API_KEY:
        return True
    supplied = request.headers.get("X-API-Key", "")
    return hmac.compare_digest(supplied.encode(), API_KEY.encode())


def validate_transaction(transaction: object) -> str | None:
    if not isinstance(transaction, dict):
        return "Expected a JSON object."

    transaction_id = transaction.get("transaction_id")
    if not isinstance(transaction_id, str) or not 1 <= len(transaction_id) <= 128:
        return "transaction_id must be a non-empty string of at most 128 characters."

    amount = transaction.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        return "amount must be numeric."
    if not 0 <= amount <= 1_000_000_000:
        return "amount must be between 0 and 1,000,000,000."

    currency = transaction.get("currency")
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        return "currency must be a three-letter code."

    merchant = transaction.get("merchant")
    if not isinstance(merchant, str) or not 1 <= len(merchant) <= 128:
        return "merchant must be a non-empty string of at most 128 characters."

    timestamp = transaction.get("timestamp")
    if not isinstance(timestamp, str) or not 1 <= len(timestamp) <= 64:
        return "timestamp must be a non-empty string of at most 64 characters."

    return None


def deterministic_reconcile(amount: float) -> tuple[str, str]:
    if amount > 1000:
        return "LLM Review", "Amount exceeds the deterministic threshold of 1000."
    return "Reconciled", "Amount is within the deterministic threshold."


@app.post("/reconcile")
def reconcile():
    if not is_authorized():
        logger.warning("Rejected unauthorized request from %s", request.remote_addr)
        return jsonify({"error": "Unauthorized."}), 401

    transaction = request.get_json(silent=True)
    error = validate_transaction(transaction)
    if error:
        return jsonify({"error": error}), 400

    status, reason = deterministic_reconcile(float(transaction["amount"]))
    result = {
        "transaction_id": transaction["transaction_id"],
        "amount": transaction["amount"],
        "currency": transaction["currency"],
        "merchant": transaction["merchant"],
        "timestamp": transaction["timestamp"],
        "status": status,
        "reason": reason,
    }
    logger.info(
        "%s | amount=%s | status=%s | %s",
        result["transaction_id"],
        result["amount"],
        result["status"],
        result["reason"],
    )
    return jsonify(result), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "Request body too large."}), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), debug=False)
