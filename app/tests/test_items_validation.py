"""Regression tests: out-of-range item input must return 422, not 500."""
import os

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")


def test_create_item_rejects_name_over_100_chars():
    """A name longer than VARCHAR(100) must be rejected with 422."""
    payload = {"name": "x" * 101, "price": 10.0, "is_offer": False}
    response = requests.post(f"{API_URL}/items", json=payload, timeout=10)
    assert response.status_code == 422


def test_create_item_accepts_name_of_exactly_100_chars():
    """A 100-char name is the upper bound and must still be accepted."""
    payload = {"name": "n" * 100, "price": 10.0, "is_offer": False}
    response = requests.post(f"{API_URL}/items", json=payload, timeout=10)
    assert response.status_code == 201
    assert response.json()["item"]["name"] == payload["name"]


def test_create_item_rejects_empty_or_blank_name():
    """Empty and whitespace-only names must be rejected with 422."""
    for bad_name in ("", "   ", "\t\n"):
        payload = {"name": bad_name, "price": 10.0, "is_offer": False}
        response = requests.post(f"{API_URL}/items", json=payload, timeout=10)
        assert response.status_code == 422, repr(bad_name)


def test_create_item_accepts_single_char_name():
    """A 1-char name is the lower bound and must still be accepted."""
    payload = {"name": "k", "price": 10.0, "is_offer": False}
    response = requests.post(f"{API_URL}/items", json=payload, timeout=10)
    assert response.status_code == 201
    assert response.json()["item"]["name"] == "k"


def test_create_item_strips_surrounding_whitespace_from_name():
    """Surrounding whitespace is stripped before the name is stored."""
    payload = {"name": "  Padded Name  ", "price": 10.0, "is_offer": False}
    response = requests.post(f"{API_URL}/items", json=payload, timeout=10)
    assert response.status_code == 201
    assert response.json()["item"]["name"] == "Padded Name"


def test_create_item_rejects_price_overflowing_numeric_10_2():
    """Prices that overflow NUMERIC(10, 2) must be rejected with 422."""
    for bad_price in (100000000, 1e8, 1e12):
        payload = {"name": "Overflow Price Item", "price": bad_price, "is_offer": False}
        response = requests.post(f"{API_URL}/items", json=payload, timeout=10)
        assert response.status_code == 422, bad_price


def test_create_item_accepts_max_price():
    """99999999.99 is the largest NUMERIC(10, 2) value and must be accepted."""
    payload = {"name": "Max Price Item", "price": 99999999.99, "is_offer": False}
    response = requests.post(f"{API_URL}/items", json=payload, timeout=10)
    assert response.status_code == 201
    assert response.json()["item"]["price"] == payload["price"]


def test_get_items_rejects_out_of_range_limit():
    """limit must be between 1 and 100; anything else returns 422."""
    for bad_limit in (-1, 0, 101, 1000000):
        response = requests.get(f"{API_URL}/items", params={"limit": bad_limit}, timeout=10)
        assert response.status_code == 422, bad_limit


def test_get_items_accepts_limit_bounds():
    """The boundary values 1 and 100 are valid limits."""
    for limit in (1, 100):
        response = requests.get(f"{API_URL}/items", params={"limit": limit}, timeout=10)
        assert response.status_code == 200, limit
        assert len(response.json()["items"]) <= limit
