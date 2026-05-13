from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from tools.license_server import LicenseServer


@dataclass
class RequestResult:
    status_code: int
    ok: bool
    code: str | None
    elapsed_ms: float
    token: str | None = None
    error: str | None = None


def write_codes(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "codes": {
                    "STRESS-SINGLE": {
                        "max_devices": 1,
                        "expires_at": "2027-12-31T23:59:59Z",
                        "disabled": False,
                        "devices": {},
                    },
                    "STRESS-IDEMPOTENT": {
                        "max_devices": 1,
                        "expires_at": "2027-12-31T23:59:59Z",
                        "disabled": False,
                        "devices": {},
                    },
                    "STRESS-VERIFY": {
                        "max_devices": 1,
                        "expires_at": "2027-12-31T23:59:59Z",
                        "disabled": False,
                        "devices": {},
                    },
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def post_json(url: str, path: str, payload: dict[str, Any], timeout: float = 8.0) -> RequestResult:
    started = time.perf_counter()
    try:
        response = requests.post(f"{url}{path}", json=payload, timeout=timeout)
        elapsed = (time.perf_counter() - started) * 1000
        try:
            data = response.json()
        except ValueError:
            data = {"ok": False, "message": response.text[:200]}
        return RequestResult(
            status_code=response.status_code,
            ok=bool(data.get("ok")),
            code=data.get("code"),
            elapsed_ms=elapsed,
            token=data.get("token"),
        )
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return RequestResult(status_code=0, ok=False, code=None, elapsed_ms=elapsed, error=repr(exc))


def run_parallel(workers: int, count: int, func) -> list[RequestResult]:
    results: list[RequestResult] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(func, index) for index in range(count)]
        for future in as_completed(futures):
            results.append(future.result())
    return results


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percent))))
    return ordered[index]


def summarize(results: list[RequestResult]) -> dict[str, Any]:
    latencies = [result.elapsed_ms for result in results]
    by_status: dict[str, int] = {}
    by_code: dict[str, int] = {}
    errors: list[str] = []
    for result in results:
        by_status[str(result.status_code)] = by_status.get(str(result.status_code), 0) + 1
        code = result.code or ("OK" if result.ok else "NO_CODE")
        by_code[code] = by_code.get(code, 0) + 1
        if result.error:
            errors.append(result.error)
    return {
        "total": len(results),
        "ok": sum(1 for result in results if result.ok),
        "failed": sum(1 for result in results if not result.ok),
        "by_status": by_status,
        "by_code": by_code,
        "latency_ms": {
            "min": round(min(latencies), 2) if latencies else 0,
            "mean": round(statistics.mean(latencies), 2) if latencies else 0,
            "p95": round(percentile(latencies, 0.95), 2),
            "max": round(max(latencies), 2) if latencies else 0,
        },
        "errors": errors[:10],
    }


def assert_condition(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run concurrent activation-code stress tests against the demo license server.")
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--same-code-requests", type=int, default=64)
    parser.add_argument("--same-device-requests", type=int, default=64)
    parser.add_argument("--verify-requests", type=int, default=200)
    parser.add_argument("--invalid-requests", type=int, default=64)
    parser.add_argument("--report", type=Path, default=Path("release/test-reports/license-stress.json"))
    args = parser.parse_args()

    report: dict[str, Any] = {
        "ok": False,
        "scenarios": {},
        "settings": {
            "workers": args.workers,
            "same_code_requests": args.same_code_requests,
            "same_device_requests": args.same_device_requests,
            "verify_requests": args.verify_requests,
            "invalid_requests": args.invalid_requests,
            "report": str(args.report),
        },
    }
    with tempfile.TemporaryDirectory(prefix="doubao-license-stress-") as tmp:
        codes_path = Path(tmp) / "codes.json"
        write_codes(codes_path)
        server = LicenseServer(("127.0.0.1", 0), codes_path, "stress-secret")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        report["server_url"] = base_url

        try:
            single_results = run_parallel(
                args.workers,
                args.same_code_requests,
                lambda index: post_json(
                    base_url,
                    "/api/activate",
                    {
                        "activation_code": "STRESS-SINGLE",
                        "device_id": f"device-{index}",
                        "app_version": "0.2.0",
                    },
                ),
            )
            report["scenarios"]["single_code_device_limit"] = summarize(single_results)
            assert_condition(
                sum(1 for result in single_results if result.ok) == 1,
                "single-device activation code allowed more or fewer than one device",
            )
            assert_condition(
                sum(1 for result in single_results if result.code == "DEVICE_LIMIT")
                == args.same_code_requests - 1,
                "single-device activation code did not reject the remaining devices",
            )

            idempotent_results = run_parallel(
                args.workers,
                args.same_device_requests,
                lambda _index: post_json(
                    base_url,
                    "/api/activate",
                    {
                        "activation_code": "STRESS-IDEMPOTENT",
                        "device_id": "same-device",
                        "app_version": "0.2.0",
                    },
                ),
            )
            report["scenarios"]["same_device_idempotency"] = summarize(idempotent_results)
            assert_condition(
                all(result.ok for result in idempotent_results),
                "same-device repeated activation should stay idempotent",
            )

            activation = post_json(
                base_url,
                "/api/activate",
                {
                    "activation_code": "STRESS-VERIFY",
                    "device_id": "verify-device",
                    "app_version": "0.2.0",
                },
            )
            assert_condition(activation.ok and bool(activation.token), "failed to create token for verify stress test")
            verify_results = run_parallel(
                args.workers,
                args.verify_requests,
                lambda _index: post_json(
                    base_url,
                    "/api/verify",
                    {
                        "token": activation.token,
                        "device_id": "verify-device",
                        "app_version": "0.2.0",
                    },
                ),
            )
            report["scenarios"]["token_verify"] = summarize(verify_results)
            assert_condition(all(result.ok for result in verify_results), "token verify stress test had failures")

            invalid_results = run_parallel(
                args.workers,
                args.invalid_requests,
                lambda index: post_json(
                    base_url,
                    "/api/activate",
                    {
                        "activation_code": f"INVALID-{index}",
                        "device_id": f"invalid-device-{index}",
                        "app_version": "0.2.0",
                    },
                ),
            )
            report["scenarios"]["invalid_codes"] = summarize(invalid_results)
            assert_condition(
                all(result.code == "UNKNOWN_CODE" for result in invalid_results),
                "invalid activation codes should all return UNKNOWN_CODE",
            )
            report["ok"] = True
        except Exception as exc:
            report["error"] = repr(exc)
            raise
        finally:
            server.shutdown()
            thread.join(timeout=5)
            report["final_codes"] = json.loads(codes_path.read_text(encoding="utf-8"))
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
