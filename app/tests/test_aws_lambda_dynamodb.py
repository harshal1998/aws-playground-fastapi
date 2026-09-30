import os
import time

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")

# Deploys wait (bounded) for the function to become Active/Updated, so they
# can take longer than a plain request on a cold LocalStack.
LAMBDA_DEPLOY_TIMEOUT = 60
LAMBDA_INVOKE_TIMEOUT = 30


def _deploy_lambda(name: str, code: str) -> requests.Response:
    return requests.post(
        f"{API_URL}/aws/lambda/functions",
        json={"name": name, "code": code},
        timeout=LAMBDA_DEPLOY_TIMEOUT,
    )


def _invoke_lambda(name: str, payload: dict) -> requests.Response:
    """Invokes a function, retrying briefly while LocalStack cold-starts it."""
    for attempt in range(5):
        res = requests.post(
            f"{API_URL}/aws/lambda/invoke",
            json={"name": name, "payload": payload},
            timeout=LAMBDA_INVOKE_TIMEOUT,
        )
        if res.status_code == 200 or attempt == 4:
            return res
        time.sleep(2)
    return res


def test_aws_lambda_handler_error_reports_failure():
    """Verify an invoke whose handler raises returns executed=false with the error payload."""
    fn_name = "pytest_raising_fn"
    deploy_res = _deploy_lambda(
        fn_name,
        "def lambda_handler(event, context):\n    raise ValueError('boom from pytest')\n",
    )
    assert deploy_res.status_code == 200, deploy_res.text

    invoke_res = _invoke_lambda(fn_name, {"x": 1})
    assert invoke_res.status_code == 200, invoke_res.text
    data = invoke_res.json()
    assert data["executed"] is False
    assert data["error"]
    assert "boom from pytest" in data["result"]["errorMessage"]
    assert data["result"]["errorType"] == "ValueError"

    requests.delete(f"{API_URL}/aws/lambda/functions", params={"name": fn_name}, timeout=30)


def test_aws_lambda_redeploy_updates_code_in_place():
    """Verify redeploying an existing function updates its code and keeps its ARN."""
    fn_name = "pytest_redeploy_fn"
    requests.delete(f"{API_URL}/aws/lambda/functions", params={"name": fn_name}, timeout=30)

    first = _deploy_lambda(fn_name, "def lambda_handler(event, context):\n    return {'version': 1}\n")
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "created"

    res_v1 = _invoke_lambda(fn_name, {})
    assert res_v1.status_code == 200, res_v1.text
    assert res_v1.json()["result"] == {"version": 1}

    second = _deploy_lambda(fn_name, "def lambda_handler(event, context):\n    return {'version': 2}\n")
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "updated"
    assert second.json()["arn"] == first.json()["arn"]

    res_v2 = _invoke_lambda(fn_name, {})
    assert res_v2.status_code == 200, res_v2.text
    assert res_v2.json()["executed"] is True
    assert res_v2.json()["result"] == {"version": 2}

    requests.delete(f"{API_URL}/aws/lambda/functions", params={"name": fn_name}, timeout=30)


def test_aws_dynamodb_native_types_round_trip():
    """Verify None, nested maps/lists, exponent numbers and booleans round-trip natively."""
    table = "test_pytest_native_types"
    create_res = requests.post(
        f"{API_URL}/aws/dynamodb/tables",
        json={"table_name": table, "key_name": "id"},
    )
    assert create_res.status_code == 200

    item = {
        "id": "native-1",
        "n": None,
        "obj": {"x": [1, 2], "nested": {"deep": [True, None, "s"]}},
        "tags": ["a", "b"],
        "big": 1e5,
        "price": 99.99,
        "count": 3,
        "active": True,
        "archived": False,
    }
    put_res = requests.post(
        f"{API_URL}/aws/dynamodb/items",
        json={"table_name": table, "item": item},
    )
    assert put_res.status_code == 200, put_res.text

    scan_res = requests.get(f"{API_URL}/aws/dynamodb/items", params={"table_name": table})
    assert scan_res.status_code == 200, scan_res.text
    stored = next(it for it in scan_res.json()["items"] if it.get("id") == "native-1")

    assert stored["n"] is None
    assert stored["obj"] == {"x": [1, 2], "nested": {"deep": [True, None, "s"]}}
    assert stored["tags"] == ["a", "b"]
    assert stored["big"] == 100000
    assert stored["price"] == 99.99
    assert stored["count"] == 3
    assert stored["active"] is True
    assert stored["archived"] is False

    requests.delete(f"{API_URL}/aws/dynamodb/tables", params={"table_name": table})


def test_aws_dynamodb_scan_missing_table_reports_error():
    """Verify scanning a table that does not exist fails instead of returning []."""
    scan_res = requests.get(
        f"{API_URL}/aws/dynamodb/items",
        params={"table_name": "test_pytest_table_that_does_not_exist"},
    )
    assert scan_res.status_code == 404
