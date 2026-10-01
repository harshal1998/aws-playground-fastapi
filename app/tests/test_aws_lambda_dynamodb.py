"""Integration tests for Lambda error reporting/redeploys and DynamoDB native types.

Function and table names are unique per run and removed in fixture teardown
(see conftest.py). The missing-table scan 404 is covered in
test_backend_errors_cache.py.
"""


def test_aws_lambda_handler_error_reports_failure(function_name, deploy_lambda, invoke_lambda):
    """Verify an invoke whose handler raises returns executed=false with the error payload."""
    deploy_res = deploy_lambda(
        function_name,
        "def lambda_handler(event, context):\n    raise ValueError('boom from pytest')\n",
    )
    assert deploy_res.status_code == 200, deploy_res.text

    invoke_res = invoke_lambda(function_name, {"x": 1})
    assert invoke_res.status_code == 200, invoke_res.text
    data = invoke_res.json()
    assert data["executed"] is False
    assert data["error"]
    assert "boom from pytest" in data["result"]["errorMessage"]
    assert data["result"]["errorType"] == "ValueError"


def test_aws_lambda_redeploy_updates_code_in_place(function_name, deploy_lambda, invoke_lambda):
    """Verify redeploying an existing function updates its code and keeps its ARN."""
    first = deploy_lambda(function_name, "def lambda_handler(event, context):\n    return {'version': 1}\n")
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "created"

    res_v1 = invoke_lambda(function_name, {})
    assert res_v1.status_code == 200, res_v1.text
    assert res_v1.json()["result"] == {"version": 1}

    second = deploy_lambda(function_name, "def lambda_handler(event, context):\n    return {'version': 2}\n")
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "updated"
    assert second.json()["arn"] == first.json()["arn"]

    res_v2 = invoke_lambda(function_name, {})
    assert res_v2.status_code == 200, res_v2.text
    assert res_v2.json()["executed"] is True
    assert res_v2.json()["result"] == {"version": 2}


def test_aws_dynamodb_native_types_round_trip(api, table_name):
    """Verify None, nested maps/lists, exponent numbers and booleans round-trip natively."""
    create_res = api.post("/aws/dynamodb/tables", json={"table_name": table_name, "key_name": "id"})
    assert create_res.status_code == 200, create_res.text

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
    put_res = api.post("/aws/dynamodb/items", json={"table_name": table_name, "item": item})
    assert put_res.status_code == 200, put_res.text

    scan_res = api.get("/aws/dynamodb/items", params={"table_name": table_name})
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
