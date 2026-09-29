import random

from locust import HttpUser, between, task


class FastAPITestUser(HttpUser):
    wait_time = between(0.01, 0.05)

    # Weight 5: Read items from DB (simulating read-heavy traffic)
    @task(5)
    def test_read_items(self):
        self.client.get("/items?limit=10", name="/items [DB Read]")

    # Weight 2: Write a new item to PostgreSQL
    @task(2)
    def test_create_item(self):
        rand_id = random.randint(1, 100000)
        self.client.post(
            "/items",
            json={
                "name": f"Product_{rand_id}",
                "price": round(random.uniform(9.99, 499.99), 2),
                "is_offer": random.choice([True, False]),
            },
            name="/items [DB Write]",
        )

    # Weight 1: Basic endpoint
    @task(1)
    def test_root_endpoint(self):
        self.client.get("/", name="/ [Root]")
