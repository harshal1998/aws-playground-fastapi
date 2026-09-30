# Adding a New AWS Service Integration

The `aws` router (SQS, DynamoDB, Secrets Manager, Lambda, EventBridge, Kinesis) follows the same
six-step pattern for every service. Use this as a template when adding a new one (e.g. SNS, SSM).

## The pattern

1. **Enable it in LocalStack** — add the service name to `SERVICES=` in `compose.yml`'s
   `localstack.environment` block. See [Environment Variables](environment-variables.md#localstack-service-enablement).

2. **Create the boto3 client in `AWSService.__init__`** in `app/services/aws.py`, next to the
   others:
   ```python
   self.sns = self._get_boto_client("sns")
   ```
   `_get_boto_client()` builds it from the service's private `boto3.session.Session` and applies
   the shared `BOTO_CLIENT_CONFIG` from `app/core/boto.py` (connect/read timeouts and retry
   attempts). Don't construct `boto3.client(...)` directly or create clients lazily: the default
   session isn't thread-safe, and the singleton is built once at startup. List operations should
   use `_paginate(client, "list_...", "ResultKey")` so they don't stop at the first page.

3. **Add request/response schemas** in `app/schemas/aws.py` (plain Pydantic `BaseModel`s, one per
   operation that needs a JSON body — GET/DELETE endpoints in this codebase use `Query(...)`
   params instead of schemas):
   ```python
   class SNSTopicCreate(BaseModel):
       name: str
   ```

4. **Add service methods** on `AWSService` in `app/services/aws.py`. Follow the existing
   conventions:
   - Let boto3 errors (`ClientError`, `BotoCoreError`) propagate from every method, including
     list operations. Don't return `[]` on error: an empty list would hide "LocalStack down" as
     "nothing here". The handlers in `app/api/errors.py` turn them into `{"detail": ...}`
     responses: not-found codes → 404, validation → 400, conflict/in-use → 409, throttling → 429,
     connection errors/timeouts → 503, anything else → 502. If the new service uses an error
     code the handlers don't know, add it to the matching set there.
   - Catch a `ClientError` only for intentional behaviour, e.g. returning
     `{"status": "already_exists"}` on `ResourceInUseException` (see `create_dynamodb_table`),
     and re-raise every other code. Inside a list, a per-item describe call may catch
     `ClientError` (a resource deleted mid-listing), but never `Exception`.
   - Add a module-level passthrough function at the bottom of the file (backwards-compat alias
     pattern already used for every other service) if you want it importable without going through
     `get_aws_service()`.

5. **Add routes** in `app/api/v1/endpoints/aws.py`, grouped under a `# --- ServiceName Endpoints ---`
   comment block. Call the service method directly: no `try/except Exception` → `HTTPException(400)`
   wrapper, because the central handlers map errors to the right status. Raise `HTTPException`
   yourself only for app-level checks (e.g. the S3 upload size 413). No new router registration is
   needed — `aws.router` is already mounted at `/aws` in `app/api/v1/router.py`.

6. **Add an integration test** under `app/tests/` (for example a new `test_<service>.py`, as
   `test_aws_lambda_dynamodb.py` does) following the `test_aws_*_lifecycle` naming convention:
   create → verify via list/scan → (update if applicable) → the test suite runs against a live
   stack, so no mocking is needed or expected.

## Things to double check

- LocalStack Community Edition doesn't support every AWS service (e.g. no Step Functions). Check
  the [LocalStack feature coverage](https://docs.localstack.cloud/references/coverage/) before
  building the integration.
- Resource names created by tests (`test-pytest-*`, `test_pytest_*`) are not cleaned up between
  runs — LocalStack state resets when the container is recreated (`docker compose down -v`), not
  automatically per test run. If you add a lifecycle test, either tolerate `ResourceInUseException`
  and treat it as success (as `create_dynamodb_table` and `create_kinesis_stream` in
  `app/services/aws.py` do) or pick a unique name (e.g. a `uuid` suffix) and delete what you
  create.
- If you want the new service exposed in the Developer Portal UI (`docker/portal/`), that's a
  separate, manual step in `docker/portal/js/aws.js` and the relevant partial under
  `docker/portal/partials/` — it is not auto-generated from the FastAPI routes.
