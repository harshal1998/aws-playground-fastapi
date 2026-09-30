import os

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")


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
    assert scan_res.status_code == 400
