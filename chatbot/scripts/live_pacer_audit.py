import json
import threading
import time
from datetime import UTC, datetime
from rag_app.config import ROOT
from rag_app.provider import ProviderFailure
from scripts.review_meal_50_live import save_json

def install_pacer(provider, interval, ledger):
    original = provider.client.post
    lock = threading.Lock()
    last = [0.0]
    pace_file = ROOT / "tmp/meal-eval-pacing.json"
    if pace_file.exists():
        last_at = json.loads(pace_file.read_text(encoding="utf-8"))["last_call_at"]
        elapsed = (datetime.now(UTC) - datetime.fromisoformat(last_at)).total_seconds()
        last[0] = time.monotonic() - max(0, elapsed)

    def paced(model, method, body):
        with lock:
            while time.monotonic() - last[0] < interval:
                time.sleep(min(1, interval - (time.monotonic() - last[0])))
            last[0] = time.monotonic()
            save_json(pace_file, {"last_call_at": datetime.now(UTC).isoformat()})
            print("GEMINI_CALL", method, model, flush=True)
            record = {"at": datetime.now(UTC).isoformat(), "method": method, "model": model}
            try:
                value = original(model, method, body)
                record.update(response_id=value.get("responseId"), usage=value.get("usageMetadata", {}), success=True)
                return value
            except ProviderFailure as error:
                causes = []
                current = error.__cause__
                while current is not None and len(causes) < 4:
                    causes.append(type(current).__name__)
                    current = current.__cause__
                record.update(success=False, error=str(error), cause_classes=causes)
                raise
            finally:
                ledger.append(record)
    provider.client.post = paced

