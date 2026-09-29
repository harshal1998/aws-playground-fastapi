# Adding a New AWS Service Integration

The `aws` router (SQS, DynamoDB, Secrets Manager, Lambda, EventBridge, Kinesis) follows the same
five-step pattern for every service. Use this as a template when adding a new one (e.g. SNS, SSM).

## The pattern

1. **Enable it in LocalStack** — add the service name to `SERVICES=` in `compose.yml`'s
   `localstack.environment` block. See [Environment Variables](environment-variables.md#localstack-service-enablement).

2. **Add a cached boto3 client property** in `app/services/aws.py`'s `AWSService` class:
   ```python
   @cached_property
   def sns(self):
       """Cached SNS boto3 client."""
       return self._get_boto_client("sns")
   ```

3. **Add request/response schemas** in `app/schemas/aws.py` (plain Pydantic `BaseModel`s, one per
   operation that needs a JSON body — GET/DELETE endpoints in this codebase use `Query(...)`
   params instead of schemas):
   ```python
   class SNSTopicCreate(BaseModel):
       name: str
   ```

4. **Add service methods** on `AWSService` in `app/services/aws.py`. Follow the existing
   conventions:
   - List operations: wrap in `try/except Exception`, `print()` the error, and return an empty
     list/dict rather than raising — the frontend/portal expects a shape, not an error, from list
     endpoints.
   - Mutating operations (create/put/delete): let exceptions propagate as `ClientError` (or let
     the endpoint catch and convert to `HTTPException`), since the caller needs to know a write
     failed.
   - Add a module-level passthrough function at the bottom of the file (backwards-compat alias
     pattern already used for every other service) if you want it importable without going through
     `get_aws_service()`.

5. **Add routes** in `app/api/v1/endpoints/aws.py`, grouped under a `# --- ServiceName Endpoints ---`
   comment block, each wrapped in `try/except Exception: raise HTTPException(400, str(e))` for
   mutating calls. No new router registration is needed — `aws.router` is already mounted at
   `/aws` in `app/api/v1/router.py`.

6. **Add an integration test** in `app/tests/test_api.py` following the `test_aws_*_lifecycle`
   naming convention: create → verify via list/scan → (update if applicable) → the test suite runs
   against a live stack, so no mocking is needed or expected.

## Things to double check

- LocalStack Community Edition doesn't support every AWS service (e.g. no Step Functions). Check
  the [LocalStack feature coverage](https://docs.localstack.cloud/references/coverage/) before
  building the integration.
- Resource names created by tests (`test-pytest-*`, `test_pytest_*`) are not cleaned up between
  runs — LocalStack state resets when the container is recreated (`docker compose down -v`), not
  automatically per test run. If you add a lifecycle test, either tolerate `ResourceInUseException`
  and treat it as success (see `create_sqs_queue` callers) or pick a unique name.
- If you want the new service exposed in the Developer Portal UI (`docker/portal/`), that's a
  separate, manual step in `docker/portal/js/aws.js` and the relevant partial under
  `docker/portal/partials/` — it is not auto-generated from the FastAPI routes.
