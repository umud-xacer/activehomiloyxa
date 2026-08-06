# messaging -- requirement traceability matrix (Task P-10)

Maps each requirement/invariant this module satisfies to its implementing code and the named
test that proves it. Mirrors `billing/TRACEABILITY.md`'s shape exactly.

## Functional requirements (SRS)

| Requirement | Summary | Code | Test |
|---|---|---|---|
| FR-MSG-001 | Start an internal chat with a listing owner; record a chat-initiation event | `ConversationUseCases.start_conversation`; `Conversation.start` | `test_conversation.py::TestConversationStart`; `test_conversation_use_cases.py::TestStartConversation`; `test_api.py::TestStartConversation` |
| FR-MSG-002 | Deliver chat messages in real time; persist conversation history | `messaging.interfaces.ws.messaging_websocket`; `RedisRealtimePublisherAdapter`/`RedisMessageSubscriber`; `SqlalchemyConversationRepository` | `integration/test_realtime_delivery_live.py::test_a_published_message_is_delivered_over_redis_and_persisted_to_postgres` |
| FR-MSG-003 | Reveal a seller's phone number per privacy settings; record a phone-reveal event | `ConversationUseCases.reveal_phone`; `identity.interfaces.ports.ContactPolicyPort.reveal_phone` | `test_conversation_use_cases.py::TestRevealPhone`; `test_api.py::TestRevealPhone` |
| FR-MSG-004 | Block a user, preventing further contact | `BlockUseCases.block_user`; `Conversation.start`/`send_message`'s own block-enforcement guard | `test_block.py`; `test_block_use_cases.py`; `test_conversation.py::TestI19BlockEnforcementInsideTheAggregate`; `test_api.py::TestBlocks::test_I19_a_blocked_user_cannot_message_the_blocker` |
| FR-MSG-005 | Report a conversation or user for abuse | `ReportUseCases.create_report` (publishes `ContentReported`; moderation case handling is BC-11's own, out of this task's scope) | `test_report_use_cases.py`; `test_api.py::TestCreateReport` |

## Domain invariants (DDD Sec 9)

| Invariant | Text | Code | Named test |
|---|---|---|---|
| I-19 | A Conversation has exactly two participants; a blocked user can neither initiate nor continue contact with the blocker. | `ParticipantPair.__post_init__` (`SelfConversationError`); `Conversation.start`/`send_message` (`BlockedParticipantError`, `NotAParticipantError`) -- both clauses checked INSIDE the aggregate, not only by the calling use case | `test_conversation.py::TestI19ExactlyTwoParticipants`, `TestI19BlockEnforcementInsideTheAggregate`; `test_conversation_use_cases.py`'s own `test_I19_*` scenarios (5); `test_api.py`'s own `test_I19_*` scenarios (3) |
| I-18 | A phone number is revealed only per its owner's PrivacySettings; every reveal is recorded as a metric. | `ConversationUseCases.reveal_phone`; `identity.infrastructure.public_port_adapters.ContactPolicyPortAdapter.reveal_phone` | `test_conversation_use_cases.py::TestRevealPhone`; `apps/backend/tests/identity/test_public_port_adapters.py::test_reveal_phone_*` (4 tests) |

## Business rules / decisions

| Rule | Summary | Code | Test |
|---|---|---|---|
| DEC-11 | Realtime chat runs on a separate stateful tier; the HTTP tier stays stateless | `apps/backend/src/realtime_main.py` (separate app/process); `messaging.interfaces.ws.realtime_router` mounted there only | `test_api.py::TestStatelessHttpTier` (all 3 scenarios: HTTP tier has no WS route, realtime app does, realtime app has no REST business routes) |
| BR-MSG-03 | Per-user messaging rate limits on both conversation initiation and message send | `messaging.domain.policies.MessageRateLimitPolicy`; `ConversationRepository.count_recent_messages_by_author` | `test_policies.py`; `test_conversation_use_cases.py::TestStartConversation::test_rate_limit_exceeded_raises` |
| BRULE-13 | Phone reveal gated by privacy settings, authenticated, metered | `ConversationUseCases.reveal_phone` (participant check + `ContactPolicyPort.reveal_phone` + `PhoneRevealed` event) | `test_conversation_use_cases.py::TestRevealPhone`; `test_api.py::TestRevealPhone::test_PII_refused_reveal_never_exposes_a_phone_number` |
| DEC-09 (outbox, no dual-write) | Every messaging event published via the transactional outbox, same transaction as its triggering state change | `FakeOutbox`/`OutboxWriter`, called inside every use case's own session | `test_conversation_use_cases.py` (event-emission assertions across all use cases) |
| Physical DB Design (append-only messages) | `Message` has no `AggregateMixin`; only `delivered_at`/`read_at` mutate post-insert | `MessageRow`; `SqlalchemyConversationRepository.save` (`session.merge()`, not wholesale replace) | `integration/test_repository_live.py::test_conversation_save_appends_a_new_message`, `test_conversation_save_persists_delivered_at` |

## The listing-owner projection and the catalog-outbox wiring fix

| Concern | Code | Test |
|---|---|---|
| `startConversation`'s recipient resolved server-side from `listingId`, never client-asserted | `ConversationUseCases.start_conversation`; `ListingOwnerReaderPort`/`SqlalchemyListingOwnerProjectionReader` | `test_conversation_use_cases.py::TestStartConversation::test_resolves_recipient_from_the_listing_owner_projection`, `test_raises_listing_owner_unknown_when_projection_is_empty` |
| The projection is rebuilt from catalog's own `ListingCreated` event, idempotently, without messaging importing catalog | `messaging.infrastructure.event_projection.handle_listing_created` | `integration/test_event_projection_live.py` (3 tests: first delivery, redelivery no-op, malformed payload ignored) |
| Catalog's outbox has exactly ONE dispatcher (search's own routing + messaging's projection, combined) -- not two racing ones | `composition_root.make_catalog_outbox_fanout_handler`/`provide_catalog_outbox_fanout_dispatcher`; `search_worker.py` | Manually verified via `search_worker.py`'s own updated entrypoint (no automated test spans two separate worker processes; the combined handler's own two halves are each independently tested: search's own suite for `make_search_event_handler`, `integration/test_event_projection_live.py` for `handle_listing_created`) |

## Boundary / dependency

| Concern | Code | Test |
|---|---|---|
| Messaging has no static import of catalog (AIR-10) | `tools/importlinter.cfg`'s `cross-module-messaging` contract | `test_boundary_import.py::test_I01_cross_module_messaging_contract_currently_passes`, `test_I02_a_deliberate_catalog_import_breaks_the_contract_then_reverts` |
| Messaging DOES import `identity.interfaces` directly (permitted, purpose-built) | `messaging.application.ports` re-exports `identity.interfaces.ports.ContactPolicyPort` | `test_boundary_import.py` (confirms `identity.domain`/`identity.infrastructure` are still forbidden; only `identity.interfaces` is permitted) |

## Validation checklist cross-reference (P-10 prompt)

| Checklist item | Evidence |
|---|---|
| A conversation has exactly two participants; no third party can join or read it (I-19) | `test_conversation.py::TestI19ExactlyTwoParticipants`; `test_api.py::TestGetConversationAndMessages::test_I19_third_party_gets_403` |
| A blocked user cannot message the blocker; enforced in the DOMAIN, not only the API layer (I-19) | `test_conversation.py::TestI19BlockEnforcementInsideTheAggregate` (calls the aggregate's own methods directly, bypassing the use case, to prove the guard lives inside `Conversation` itself) |
| The realtime gateway runs as a SEPARATE stateful process/container; the HTTP tier holds no connection state | `apps/backend/src/realtime_main.py`; `test_api.py::TestStatelessHttpTier` (3 tests) |
| Business logic is NOT duplicated between the realtime runner and the HTTP tier | Both `interfaces/routers.py` and `interfaces/ws.py` call only `messaging.application`'s own use case classes; neither reimplements `Conversation`'s own guarded methods |
| Messages persisted to PostgreSQL AND fanned out via Redis pub/sub; Redis is a bus, never the source of truth | `integration/test_realtime_delivery_live.py` (asserts both persistence and delivery from one published message) |
| Phone reveal gated by the counterparty's privacy settings; a refused reveal exposes nothing | `test_api.py::TestRevealPhone::test_PII_refused_reveal_never_exposes_a_phone_number` |
| A successful phone reveal emits the PhoneRevealed metric EVENT; messaging stores no metric counters | `test_conversation_use_cases.py::TestRevealPhone::test_returns_the_number_when_the_counterpart_allows` (asserts the event, not a counter -- messaging has no counter storage of any kind) |
| Phone numbers and message content handled per PII rules -- never logged | No `logger.*` call anywhere in `messaging/` touches `body`/phone values; `reveal_phone`'s own docstring flags the discipline explicitly |
| Rate limiting enforced per documented limits (not invented thresholds) | `messaging/README.md` "Rate limiting" section documents the constant as an explicit, flagged implementation choice (no literal number exists in the approved documents), matching identity's own precedented resolution of the identical situation |
| messaging imports ONLY shared_kernel and identity -- import-linter enforces this | `test_boundary_import.py`; `lint-imports` (`cross-module-messaging` KEPT, 49/49 contracts) |
| Every messaging OpenAPI operation implemented; contract conformance green | `test_api.py` (all 10 operations exercised end-to-end via `TestClient` + `main.create_app()`) |
| Authorization matrix (QG-08) extended and green | Deliberately NOT extended -- messaging has zero permission-gated operations (see README "Known gaps" #6 for the full reasoning); I-19's own ownership/participant checks are proven directly instead |
| Coverage floors met; mypy --strict/ruff/import-linter clean | See README "Coverage / quality gates": domain 98.90%, application 96.61%, overall 81.14%; mypy/ruff/bandit clean; 49/49 import-linter contracts kept |
