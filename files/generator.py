import os
import random
import time
from datetime import datetime, timezone
from uuid import uuid4

import requests

TARGET_URL = os.environ.get("RECONCILE_URL", "http://10.20.1.10:8080/reconcile")
API_KEY = os.environ.get("RECONCILE_API_KEY", "")
INTERVAL_SECONDS = float(os.environ.get("INTERVAL_SECONDS", "3"))
MERCHANTS = [
    "Acme Retail",
    "Nova Electronics",
    "Bluewave Foods",
    "Orbit Travel",
    "Summit Services",
]
RNG = random.SystemRandom()


def build_transaction() -> dict:
    return {
        "transaction_id": str(uuid4()),
        "amount": round(RNG.uniform(5.0, 5000.0), 2),
        "currency": "USD",
        "merchant": RNG.choice(MERCHANTS),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    session = requests.Session()
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    while True:
        transaction = build_transaction()
        try:
            response = session.post(
                TARGET_URL,
                json=transaction,
                headers=headers,
                timeout=5,
            )
            response.raise_for_status()
            print(
                f"Sent {transaction['transaction_id']} "
                f"amount={transaction['amount']} "
                f"status={response.status_code}",
                flush=True,
            )
        except requests.RequestException as error:
            print(
                f"Failed to send {transaction['transaction_id']}: {error}",
                flush=True,
            )
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Generator stopped.", flush=True)
