"""Multithreaded load testing script for benchmarking FastAPI container RPS."""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter

URL = os.getenv("BENCHMARK_URL", "http://localhost:8000/")
TOTAL_REQUESTS = int(os.getenv("TOTAL_REQUESTS", "10000"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "1000"))


def send_request(session, req_id):
    try:
        response = session.get(URL)
        return response.status_code
    except requests.RequestException as e:
        return f"Error: {e}"


def main():
    print(f"Starting load test on {URL} with {TOTAL_REQUESTS} requests ({CONCURRENCY} concurrency)...")
    start_time = time.time()

    adapter = HTTPAdapter(pool_connections=CONCURRENCY, pool_maxsize=CONCURRENCY)
    with requests.Session() as session:
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
            futures = [
                executor.submit(send_request, session, i)
                for i in range(TOTAL_REQUESTS)
            ]

            success_count = 0
            error_count = 0

            for future in as_completed(futures):
                status = future.result()
                if status == 200:
                    success_count += 1
                else:
                    error_count += 1
                    if error_count <= 5:
                        print(f"Failed request: {status}")

    elapsed_time = time.time() - start_time
    print("\n--- Benchmark Results ---")
    print(f"Target URL:     {URL}")
    print(f"Total requests: {TOTAL_REQUESTS}")
    print(f"Concurrency:    {CONCURRENCY}")
    print(f"Success:        {success_count}")
    print(f"Failed:         {error_count}")
    print(f"Elapsed time:   {elapsed_time:.2f} seconds")
    if elapsed_time > 0:
        print(f"Throughput:     {TOTAL_REQUESTS / elapsed_time:.2f} req/s")


if __name__ == "__main__":
    main()
