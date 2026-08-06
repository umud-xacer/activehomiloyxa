# notifications -- requirement traceability matrix (Task P-13)

Maps each requirement/invariant this module satisfies to its implementing code and the named test
that proves it. Mirrors `moderation/TRACEABILITY.md`'s shape exactly.

## Functional requirements (SRS)

| Requirement | Summary | Code | Test |
|---|---|---|---|
| FR-NOTIF-001 | Every documented notification-triggering event produces a queued, templated notification for its resolved recipient | `infrastructure/event_projection.py` (7 handler functions, one per emitting module); `NotificationDispatchUseCases.queue_for_event` | `integration/test_event_projection_live.py::test_exactly_the_documented_24_events_produce_a_notification` (parametrized across all 24), `test_an_event_outside_the_documented_subset_produces_nothing` |
| FR-NOTIF-002 | Content is rendered from a `configuration`-owned template, resolved by event key + channel, localized | `ConfigurationNotificationTemplateAdapter.list_templates_for_event`; `NotificationDispatchUseCases::_resolve_text` | `test_configuration_adapter.py` (all 6 cases); `test_dispatch_use_cases.py::test_queue_for_event_renders_every_locale_correctly`, `test_falls_back_to_uz_latn_when_the_recipients_locale_has_no_translation` |
| FR-NOTIF-003 | Delivery happens over exactly the channel the template targets, via a fixed 3-channel adapter set, never leaking a provider SDK type past `infrastructure/` | `infrastructure/providers/{email,eskiz,web_push}.py`; `application/ports.py::EmailProviderPort`/`WebPushProviderPort`/`SmsProviderPort` | `test_providers.py` (all 3 adapters, each mocked at the wire boundary); `test_boundary_import.py::test_I05_provider_sdk_confined_to_infrastructure_contract_currently_passes` |
| FR-NOTIF-004 | A recipient's channel preference (email/webPush/sms) is enforced before dispatch; a suppressed delivery creates no notification row at all | `NotificationDispatchUseCases::_preference_allows` | `test_dispatch_use_cases.py::test_queue_for_event_skips_a_channel_the_recipient_has_disabled`, `test_queue_for_event_creates_no_row_at_all_when_every_channel_is_disabled` |
| FR-NOTIF-005 | The recipient's own notification list/detail/read-status endpoints are self-service, ownership-scoped | `NotificationUseCases.list_notifications`/`get_notification`/`set_notification_read`/`mark_all_notifications_read`; `interfaces/routers.py` | `test_notification_use_cases.py`; `test_api.py` (all 3 operations) |

## Domain invariants (DDD Sec 9/10.3)

| Invariant | Text | Code | Named test |
|---|---|---|---|
| I-25 | A notification's delivery status only ever advances `QUEUED -> SENT` or `QUEUED -> FAILED`, never re-enters `QUEUED` or transitions from a terminal status | `Notification.mark_sent`/`mark_failed` (both guarded by `_guard_from_queued`, raising `IllegalNotificationStateTransitionError`) | `test_notification.py::test_mark_sent_from_queued_is_legal`, `test_mark_failed_from_queued_is_legal`, `test_mark_sent_from_a_terminal_status_is_illegal`, `test_mark_failed_from_a_terminal_status_is_illegal` (both parametrized across `SENT`/`FAILED`) |
| I-26 | `read_at`/unread state is independent of delivery status -- a `FAILED` notification is still readable/markable, since the read flag tracks user attention, not delivery outcome | `Notification.mark_read`/`mark_unread` (no delivery-status guard at all, idempotent no-ops) | `test_notification.py::test_mark_read_succeeds_regardless_of_delivery_status`, `test_mark_read_twice_is_a_no_op` |

## Business rules / decisions

| Rule | Summary | Code | Test |
|---|---|---|---|
| BR-NOTIF-01 (DEC-19) | Rendered content is frozen onto the notification at creation time -- a later template edit never mutates an already-created notification | `Notification.create` copies rendered `subject`/`body` into `RenderedContent` at construction, never a live reference to the template row | `test_notification.py::test_create_freezes_rendered_content_at_construction_time` |
| BR-NOTIF-02 | Suppressed-by-preference deliveries are never created, never recorded as a `SUPPRESSED` status (no such status exists in the frozen `DeliveryStatus` enum, matching the Physical DB schema's own 3-value `delivery_status` check constraint) | `NotificationDispatchUseCases.queue_for_event` (returns before constructing a `Notification` at all when `_preference_allows` is false) | `test_dispatch_use_cases.py::test_queue_for_event_creates_no_row_at_all_when_every_channel_is_disabled` |
| DEC-18 | Provider SDK types (`smtplib`, Eskiz's `httpx` client, `pywebpush`) never cross `infrastructure/`'s own boundary | `infrastructure/providers/*.py` (only these 3 files import their respective SDK) | `test_boundary_import.py::test_I05_provider_sdk_confined_to_infrastructure_contract_currently_passes`, `test_I06_no_provider_sdk_import_appears_outside_infrastructure_by_direct_grep` |
| DEC-19 | uz_latn is canonical; every dispatch renders against the recipient's resolved locale, falling back to uz_latn when a translation is missing | `NotificationDispatchUseCases::_resolve_text`; `_DEFAULT_LOCALE` | `test_dispatch_use_cases.py::test_falls_back_to_uz_latn_when_the_recipients_locale_has_no_translation` |
| Playbook Sec 6 (transaction hygiene) | The provider call is never made inside an open DB transaction; `queue_for_event` (DB-only) and `dispatch_queued` (provider-call + DB write) are separate steps | `application/dispatch_use_cases.py`'s two-method split; `notifications_worker.py`'s own post-commit dispatch loop | `test_dispatch_use_cases.py::test_queue_for_event_never_calls_any_provider_port` |
| Security Sec 12 (PII in logs) | A failed dispatch logs only safe identifiers (notification id, channel, event key) -- never email/phone/push endpoint/subject/body | `NotificationDispatchUseCases.dispatch_queued`'s `_logger.warning(..., extra={...})` call | `test_pii_logging.py::test_a_failed_dispatch_logs_no_recipient_or_content_field` |

## Cross-context boundary

| Concern | Code | Test |
|---|---|---|
| Notifications has no static dependency on any module except `shared_kernel`/`configuration` -- stricter than most modules, forbidding even `identity` | `tools/importlinter.cfg`'s `cross-module-notifications` contract | `test_boundary_import.py::test_I01_cross_module_notifications_contract_currently_passes`, `test_I02_a_deliberate_forbidden_import_breaks_the_contract_then_reverts` (parametrized: identity/profiles/catalog/billing/ads/messaging/moderation) |
| Nothing imports notifications -- a terminal sink, same class as admin/analytics | `tools/importlinter.cfg`'s pre-existing `sink-modules-have-no-inbound-imports` contract | `test_boundary_import.py::test_I03_sink_modules_have_no_inbound_imports_contract_currently_passes` |
| No inbound command port exists for another module to call ("send a notification") | `interfaces/ports.py::NotificationPort` (3 read-only methods only) | `test_boundary_import.py::test_I04_no_inbound_command_port_exists_for_other_modules_to_call` |
| Recipient/profile/listing-owner resolution happens entirely inside `composition_root.py`, never inside `notifications/` itself | `composition_root._RecipientDirectoryBridge` (implements notifications' own `RecipientDirectoryPort`, reading identity's/profiles'/catalog's real repositories) | `test_dispatch_use_cases.py` (exercises the port via a `Fake*` implementation only -- no real cross-module import exists to test against) |
| Billing/catalog/identity/messaging's already-multi-consumer outboxes gain a notifications route folded into their EXISTING combined dispatcher, never a second competing one | `composition_root.make_billing_entitlement_fanout_handler`/`make_catalog_outbox_fanout_handler`/`make_identity_account_status_projection_handler`/`make_messaging_report_projection_handler` (all extended, not duplicated) | `integration/test_event_projection_live.py` (per-emitting-module positive cases) |
| Profiles' and moderation's own outboxes get their first-ever dispatcher, both dedicated to notifications | `composition_root.provide_profiles_notification_projection_dispatcher`/`provide_moderation_notification_projection_dispatcher`; `notifications_worker.py` | `integration/test_event_projection_live.py::test_verification_requested_produces_a_notification`, `test_moderation_action_taken_on_a_listing_produces_a_notification` |
| `InvoiceIssued` carries no recipient reference at all -- resolved via a local projection populated by that order's own preceding `OrderPlaced` event | `infrastructure/persistence/models.py::OrderRecipientProjectionRow`; `event_projection.handle_billing_event` (both routes) | `integration/test_event_projection_live.py::test_invoice_issued_resolves_the_purchaser_via_the_order_recipient_projection` |
| Idempotent event consumption via `ProcessedEvent`, one handler name per emitting module | `infrastructure/event_projection.py` (`idempotent_consume` wraps each of the 7 handlers under a distinct name) | `integration/test_event_projection_live.py::test_redelivering_the_same_event_dispatches_it_exactly_once` (parametrized) |

## No release-blocking authorization matrix contribution (by design)

| Concern | Rationale | Test |
|---|---|---|
| `notifications`-tagged operations add no `tests/authorization_matrix.py` scenario | Ownership-scoped self-service, not permission-gated -- mirrors catalog's/media's own self-service model (a listing owner reading their own draft), not moderation's/profiles' admin-gated one. A request for another user's notification returns 404 (indistinguishable from non-existent), never a 403, so there is no allow/deny permission-key matrix to extend | `test_api.py::test_get_notification_for_another_users_notification_returns_404_not_403`; `test_notification_use_cases.py::test_get_notification_raises_not_found_when_owned_by_a_different_user` |

## Validation checklist cross-reference (P-13 prompt)

| Checklist item | Evidence |
|---|---|
| Exactly the documented EventKey subset is consumed; nothing outside it is invented | README "The EventKey subset (mechanically derived, not guessed)"; `integration/test_event_projection_live.py::test_exactly_the_documented_24_events_produce_a_notification` |
| Idempotent consumption via ProcessedEvent -- redelivery dispatches once | `integration/test_event_projection_live.py::test_redelivering_the_same_event_dispatches_it_exactly_once` |
| Template resolution by event key + channel, localized to all 4 locales, with uz_latn fallback | `test_configuration_adapter.py`; `test_dispatch_use_cases.py::test_queue_for_event_renders_every_locale_correctly`, `test_falls_back_to_uz_latn_when_the_recipients_locale_has_no_translation` |
| Preference enforcement suppresses (not silently fails) a disabled channel -- no row created | `test_dispatch_use_cases.py::test_queue_for_event_creates_no_row_at_all_when_every_channel_is_disabled` |
| Three channel adapters, each strictly behind a port, no SDK leakage | `test_providers.py`; `test_boundary_import.py::test_I05`/`test_I06` |
| Fail-closed: missing credentials or a provider exception marks FAILED, never SENT, never a silent fallback | `test_dispatch_use_cases.py::test_dispatch_queued_marks_failed_when_the_provider_raises`; `test_providers.py::test_each_adapter_raises_at_construction_when_its_required_env_is_missing` |
| Dispatch worker never blocks the event loop nor holds a DB transaction across a provider call | README "Transaction hygiene"; `test_dispatch_use_cases.py::test_queue_for_event_never_calls_any_provider_port` |
| No inbound command port; nothing imports notifications | `test_boundary_import.py::test_I03`, `test_I04` |
| Only the 3 notifications-tagged OpenAPI operations are implemented; no preference-writing endpoint added here | `test_api.py` (all 3 operations); README "Public interface" |
| PII never appears in failure logs | `test_pii_logging.py::test_a_failed_dispatch_logs_no_recipient_or_content_field` |
| Excluded: template authoring, digest/saved-search alerts, any inbound send port, notifications for events without an EventKey | Not implemented anywhere in this module -- verified by absence, not a passing test |
| Coverage floors met; mypy --strict/ruff/import-linter clean | See README "Coverage / quality gates": domain/application all >= 92.6%, overall (full suite) 86.6%; mypy/ruff clean; 49/49 import-linter contracts kept |
