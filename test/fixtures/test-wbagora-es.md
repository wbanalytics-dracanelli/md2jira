# TESTING 2026-02-28 -- ES Formatting Showcase

This Epic exercises every JIRA formatting element supported by md2jira against the wbagora ES project.

h3. Business Context

The Engagement Services team needs a kitchen-sink test to verify that multi-instance support produces correctly formatted issues on a *different* Jira instance with _different_ custom field IDs.

h3. Scope

* Validate Epic, Task, and Sub-task creation
* Confirm code blocks, tables, checklists, and links render correctly
* Verify parent-child relationships across the hierarchy

h3. References

* [md2jira Repository|https://github.com/danielracanelli/md2jira]
* [Atlassian REST API Docs|https://developer.atlassian.com/cloud/jira/platform/rest/v2/]

## TESTING 2026-02-28 -- API Integration Layer

Build the integration layer that connects Engagement Services to the platform event bus.

h3. Technical Approach

The service should consume events via a lightweight polling adapter and publish responses through the existing gateway. All payloads use JSON over HTTPS.

h3. API Endpoints

{code:python}
from fastapi import FastAPI, HTTPException

app = FastAPI(title="ES Integration API")

@app.post("/api/v1/events")
async def ingest_event(event: dict):
    if "type" not in event:
        raise HTTPException(status_code=400, detail="Missing event type")
    return {"status": "accepted", "event_id": event.get("id")}

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
{code}

h3. Configuration Schema

{code:yaml}
service:
  name: es-integration
  port: 8080
  log_level: info
event_bus:
  broker: kafka
  topic: engagement.events
  group_id: es-consumer
{code}

h3. Environment Matrix

| Environment | Broker Host | Topic Prefix | Auth Method |
| --- | --- | --- | --- |
| Dev | kafka-dev.internal:9092 | dev.engagement | SASL/PLAIN |
| Staging | kafka-stg.internal:9092 | stg.engagement | SASL/SCRAM |
| Production | kafka-prod.internal:9092 | prod.engagement | mTLS |

h3. Acceptance Criteria

* Events are ingested within 200ms p99
* Failed events are dead-lettered after 3 retries
* Health endpoint returns _200 OK_ with version info

### TESTING 2026-02-28 -- Event Consumer Implementation

Implement the Kafka consumer that processes incoming engagement events.

h3. Requirements

* Connect to the configured Kafka broker
* Deserialize JSON payloads with schema validation
* Route events by type to the appropriate handler
* Emit metrics for throughput and error rate

h3. Handler Mapping

{code:python}
EVENT_HANDLERS = {
    "user.signup":     handle_signup,
    "user.engagement": handle_engagement,
    "campaign.click":  handle_campaign_click,
}

def dispatch(event: dict) -> None:
    handler = EVENT_HANDLERS.get(event["type"])
    if handler is None:
        raise UnknownEventError(event["type"])
    handler(event["payload"])
{code}

* [ ] Set up Kafka consumer with configurable group ID
* [>] Implement JSON schema validation for event payloads
* [>] Add dead-letter queue for failed events
* [x] Define event type enum and handler mapping
* [ ] Write integration tests against embedded Kafka
* [ ] Add Prometheus metrics for event throughput

### TESTING 2026-02-28 -- API Gateway Configuration

Configure the API gateway to route external traffic to the integration service.

h3. Routing Rules

| Path Pattern | Target Service | Rate Limit | Auth Required |
| --- | --- | --- | --- |
| /api/v1/events | es-integration | 1000 req/min | Yes |
| /api/v1/health | es-integration | No limit | No |
| /api/v1/metrics | es-integration | 100 req/min | Yes |

h3. Security

* All endpoints require TLS 1.3+
* Event ingestion requires a valid *API key* in the _X-API-Key_ header
* Health check is unauthenticated for load balancer probes

h3. Deployment Notes

{code:bash}
kubectl apply -f k8s/staging/es-integration.yaml
kubectl rollout status deployment/es-integration -n engagement
kubectl logs -f deployment/es-integration -n engagement --tail=100
{code}

* [ ] Create Kubernetes deployment manifest
* [ ] Configure horizontal pod autoscaler (min 2, max 8)
* [x] Set up service mesh sidecar for mTLS
* [ ] Add readiness and liveness probes
