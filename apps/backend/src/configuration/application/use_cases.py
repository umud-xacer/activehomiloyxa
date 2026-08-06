"""The generic configuration use cases -- one class, parametrized by `ConfigEntityType` at call
time, backing all thirteen `Configuration (Admin)` operations for all eight entities (DB
Architecture Sec 18: build the machinery once, instantiate it per entity). Depends only on the
ports it declares (`application/ports.py`) plus `shared_kernel`'s `OutboxPort` -- never a
concrete adapter (Playbook Sec 6).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from configuration.application.exceptions import (
    ConfigHeadNotFoundError,
    ConfigVersionNotFoundError,
    GateFailedError,
    VersionNotPublishableError,
)
from configuration.application.ports import ConfigHeadRepository, SnapshotCachePort
from configuration.domain import (
    ApproverPermissionError,
    AuthoringTrack,
    ConfigEntityType,
    ConfigHead,
    ConfigVersion,
    DuplicateCodeError,
    GateContext,
    GateResult,
    HeadStatus,
    PreActivationGate,
    VersionStatus,
    WhitelistRegistry,
    resolve_configuration_changed_event_type,
)
from shared_kernel import EventEnvelope, OutboxPort


def _structural_diff(from_doc: dict[str, Any], to_doc: dict[str, Any]) -> dict[str, Any]:
    added = {k: v for k, v in to_doc.items() if k not in from_doc}
    removed = {k: v for k, v in from_doc.items() if k not in to_doc}
    changed = {
        k: {"from": from_doc[k], "to": to_doc[k]}
        for k in from_doc
        if k in to_doc and from_doc[k] != to_doc[k]
    }
    return {"added": added, "removed": removed, "changed": changed}


class ConfigurationUseCases:
    def __init__(
        self,
        repo: ConfigHeadRepository,
        snapshot_cache: SnapshotCachePort,
        outbox: OutboxPort,
        *,
        gate: PreActivationGate | None = None,
        whitelist: WhitelistRegistry | None = None,
    ) -> None:
        self._repo = repo
        self._cache = snapshot_cache
        self._outbox = outbox
        self._gate = gate or PreActivationGate()
        self._whitelist = whitelist or WhitelistRegistry()

    async def _require_head(self, entity_type: ConfigEntityType, head_id: UUID) -> ConfigHead:
        head = await self._repo.get_head(entity_type, head_id)
        if head is None:
            raise ConfigHeadNotFoundError(entity_type.value, str(head_id))
        return head

    async def _require_version(
        self, entity_type: ConfigEntityType, head_id: UUID, version_id: UUID
    ) -> ConfigVersion:
        version = await self._repo.get_version(entity_type, head_id, version_id)
        if version is None:
            raise ConfigVersionNotFoundError(entity_type.value, str(head_id), str(version_id))
        return version

    async def _build_gate_context(
        self,
        entity_type: ConfigEntityType,
        head: ConfigHead | None,
        content: dict[str, Any],
    ) -> GateContext:
        deps: dict[str, bool] = {}
        category_has_bound_listings = False
        ancestor_codes_of_parent: frozenset[str] = frozenset()
        ancestor_codes_of_parent_role: frozenset[str] = frozenset()

        if entity_type is ConfigEntityType.CATEGORY:
            form_id = content.get("form_definition_id")
            if form_id:
                deps[f"form-definition:{form_id}"] = await self._repo.dependency_exists(
                    "form-definition", str(form_id)
                )
            parent_id = content.get("parent_category_id")
            if parent_id:
                ancestor_codes_of_parent = await self._repo.ancestor_codes(
                    entity_type, str(parent_id)
                )
            if content.get("tree_status") == "RETIRED" and head is not None:
                category_has_bound_listings = await self._repo.category_has_bound_listings(head.id)
        elif entity_type is ConfigEntityType.ROLE_DEFINITION:
            for group_code in content.get("permission_group_codes", []):
                deps[f"permission-group:{group_code}"] = await self._repo.dependency_exists(
                    "permission-group", str(group_code)
                )
            parent_role = content.get("parent_role_code")
            if parent_role:
                deps[f"role-definition:{parent_role}"] = await self._repo.dependency_exists(
                    "role-definition", str(parent_role)
                )
                ancestor_codes_of_parent_role = await self._repo.ancestor_codes(
                    entity_type, str(parent_role)
                )

        exclude_head_id = head.id if head is not None else None
        existing_codes = await self._repo.existing_codes(
            entity_type, exclude_head_id=exclude_head_id
        )

        return GateContext(
            entity_type=entity_type.value,
            existing_codes=existing_codes,
            dependency_exists=deps,
            category_has_bound_listings=category_has_bound_listings,
            ancestor_codes_of_parent=ancestor_codes_of_parent,
            ancestor_codes_of_parent_role=ancestor_codes_of_parent_role,
        )

    def _build_snapshot(
        self,
        head: ConfigHead,
        version: ConfigVersion,
        entity_type: ConfigEntityType,
        now: datetime,
    ) -> dict[str, Any]:
        return {
            **version.definition_document,
            "id": str(head.id),
            "code": head.code,
            "entityType": entity_type.value,
            "versionId": str(version.id),
            "versionNumber": version.version_number,
            "publishedAt": now.isoformat(),
        }

    # -- authoring ---------------------------------------------------------------------------

    async def create_draft(
        self,
        entity_type: ConfigEntityType,
        *,
        code: str,
        business_owner: str,
        definition: dict[str, Any],
        actor_id: UUID,
        now: datetime,
    ) -> tuple[ConfigHead, ConfigVersion]:
        existing = await self._repo.get_head_by_code(entity_type, code)
        if existing is not None:
            raise DuplicateCodeError(entity_type.value, code)

        head = ConfigHead(
            id=uuid4(),
            entity_type=entity_type,
            code=code,
            current_version_id=None,
            status=HeadStatus.DRAFT,
            business_owner=business_owner,
            created_at=now,
            created_by=actor_id,
            updated_at=now,
            updated_by=actor_id,
        )
        version = ConfigVersion(
            id=uuid4(),
            head_id=head.id,
            version_number=1,
            status=VersionStatus.DRAFT,
            definition_document=definition,
            snapshot_document=None,
            validity_from=None,
            validity_until=None,
            rollback_of_version_id=None,
            approved_by=None,
            approved_at=None,
            published_by=None,
            published_at=None,
            created_at=now,
            created_by=actor_id,
        )
        await self._repo.add_head(entity_type, head)
        await self._repo.add_version(entity_type, version)
        return head, version

    async def create_version_draft(
        self,
        entity_type: ConfigEntityType,
        head_id: UUID,
        *,
        definition: dict[str, Any],
        actor_id: UUID,
        now: datetime,
    ) -> ConfigVersion:
        await self._require_head(entity_type, head_id)
        next_number = await self._repo.latest_version_number(entity_type, head_id) + 1
        version = ConfigVersion(
            id=uuid4(),
            head_id=head_id,
            version_number=next_number,
            status=VersionStatus.DRAFT,
            definition_document=definition,
            snapshot_document=None,
            validity_from=None,
            validity_until=None,
            rollback_of_version_id=None,
            approved_by=None,
            approved_at=None,
            published_by=None,
            published_at=None,
            created_at=now,
            created_by=actor_id,
        )
        await self._repo.add_version(entity_type, version)
        return version

    async def update_draft(
        self,
        entity_type: ConfigEntityType,
        head_id: UUID,
        version_id: UUID,
        *,
        definition: dict[str, Any],
    ) -> ConfigVersion:
        version = await self._require_version(entity_type, head_id, version_id)
        updated = version.edit_draft(definition_document=definition)
        await self._repo.update_version(entity_type, updated)
        return updated

    # -- validation / publish -----------------------------------------------------------------

    async def validate(
        self, entity_type: ConfigEntityType, head_id: UUID, version_id: UUID
    ) -> GateResult:
        head = await self._require_head(entity_type, head_id)
        version = await self._require_version(entity_type, head_id, version_id)
        ctx = await self._build_gate_context(entity_type, head, version.definition_document)
        return self._gate.evaluate(entity_type.value, head.code, version.definition_document, ctx)

    async def publish(
        self,
        entity_type: ConfigEntityType,
        head_id: UUID,
        version_id: UUID,
        *,
        actor_id: UUID,
        actor_permission_keys: frozenset[str],
        approval_note: str | None,
        now: datetime,
    ) -> ConfigVersion:
        head = await self._require_head(entity_type, head_id)
        version = await self._require_version(entity_type, head_id, version_id)

        if version.status not in (
            VersionStatus.DRAFT,
            VersionStatus.VALIDATION,
            VersionStatus.APPROVAL,
        ):
            raise VersionNotPublishableError(str(version_id), version.status.value)

        checker_call = version.status is VersionStatus.APPROVAL

        if not checker_call:
            if version.status is VersionStatus.DRAFT:
                version = version.move_to_validation()

            ctx = await self._build_gate_context(entity_type, head, version.definition_document)
            gate_result = self._gate.evaluate(
                entity_type.value, head.code, version.definition_document, ctx
            )
            if not gate_result.valid:
                version = version.return_to_draft_after_failed_gate()
                await self._repo.update_version(entity_type, version)
                raise GateFailedError(gate_result)

            if head.authoring_track is AuthoringTrack.CONTROLLED:
                version = version.move_to_awaiting_approval()
                await self._repo.update_version(entity_type, version)
                return version
        else:
            # Checker's call: re-run the gate against current dependencies (Config Framework
            # Sec 2.6 applies the same "re-run on rollback" discipline to every re-entry).
            ctx = await self._build_gate_context(entity_type, head, version.definition_document)
            gate_result = self._gate.evaluate(
                entity_type.value, head.code, version.definition_document, ctx
            )
            if not gate_result.valid:
                version = version.return_to_draft_after_failed_gate()
                await self._repo.update_version(entity_type, version)
                raise GateFailedError(gate_result)

            approve_key = self._whitelist.approve_permission_key(entity_type.value)
            if approve_key not in actor_permission_keys:
                raise ApproverPermissionError(entity_type.value)

        is_new_head = head.current_version_id is None
        old_current_version_id = head.current_version_id
        snapshot = self._build_snapshot(head, version, entity_type, now)

        if checker_call:
            version = version.approve_and_publish(
                now=now,
                checker_id=actor_id,
                approval_note=approval_note,
                snapshot_document=snapshot,
            )
        else:
            version = version.publish_directly(
                now=now, publisher_id=actor_id, snapshot_document=snapshot
            )

        if old_current_version_id is not None:
            old_version = await self._repo.get_version(entity_type, head_id, old_current_version_id)
            if old_version is not None and old_version.status is VersionStatus.PUBLISHED:
                await self._repo.update_version(entity_type, old_version.deprecate())

        head = head.move_current_version(version.id, now=now, actor_id=actor_id)
        await self._repo.update_version(entity_type, version)
        await self._repo.update_head(entity_type, head)
        await self._cache.put(entity_type, head.code, snapshot)

        category_tree_status = (
            version.definition_document.get("tree_status")
            if entity_type is ConfigEntityType.CATEGORY
            else None
        )
        event_type = resolve_configuration_changed_event_type(
            entity_type,
            is_new_head=is_new_head,
            category_tree_status=category_tree_status,
        )
        payload: dict[str, Any] = {
            "action": "PUBLISH",
            "entityType": entity_type.value,
            "code": head.code,
            "beforeVersionId": str(old_current_version_id) if old_current_version_id else None,
            "afterVersionId": str(version.id),
            "approvalNote": approval_note,
        }
        event = EventEnvelope(
            event_id=uuid4(),
            event_type=event_type,
            occurred_at=now,
            actor=actor_id,
            aggregate_type=entity_type.value,
            aggregate_id=head.id,
            aggregate_version=version.version_number,
            payload=payload,
        )
        await self._outbox.append(event)

        return version

    async def rollback(
        self,
        entity_type: ConfigEntityType,
        head_id: UUID,
        *,
        target_version_id: UUID,
        actor_id: UUID,
        actor_permission_keys: frozenset[str],
        expedited: bool,
        now: datetime,
    ) -> ConfigVersion:
        await self._require_head(entity_type, head_id)
        target = await self._require_version(entity_type, head_id, target_version_id)
        next_number = await self._repo.latest_version_number(entity_type, head_id) + 1

        rollback_draft = ConfigVersion(
            id=uuid4(),
            head_id=head_id,
            version_number=next_number,
            status=VersionStatus.DRAFT,
            definition_document=target.definition_document,
            snapshot_document=None,
            validity_from=target.validity_from,
            validity_until=target.validity_until,
            rollback_of_version_id=target.id,
            approved_by=None,
            approved_at=None,
            published_by=None,
            published_at=None,
            created_at=now,
            created_by=actor_id,
        )
        await self._repo.add_version(entity_type, rollback_draft)

        note = "EXPEDITED ROLLBACK" if expedited else "ROLLBACK"
        return await self.publish(
            entity_type,
            head_id,
            rollback_draft.id,
            actor_id=actor_id,
            actor_permission_keys=actor_permission_keys,
            approval_note=note,
            now=now,
        )

    # -- queries -------------------------------------------------------------------------------

    async def list_heads(
        self, entity_type: ConfigEntityType, *, cursor: str | None, limit: int
    ) -> tuple[list[ConfigHead], str | None]:
        return await self._repo.list_heads(entity_type, cursor=cursor, limit=limit)

    async def get_head(self, entity_type: ConfigEntityType, head_id: UUID) -> ConfigHead:
        return await self._require_head(entity_type, head_id)

    async def list_versions(
        self, entity_type: ConfigEntityType, head_id: UUID
    ) -> list[ConfigVersion]:
        await self._require_head(entity_type, head_id)
        return await self._repo.list_versions(entity_type, head_id)

    async def get_version(
        self, entity_type: ConfigEntityType, head_id: UUID, version_id: UUID
    ) -> ConfigVersion:
        return await self._require_version(entity_type, head_id, version_id)

    async def compare_versions(
        self, entity_type: ConfigEntityType, head_id: UUID, from_id: UUID, to_id: UUID
    ) -> dict[str, Any]:
        from_version = await self._require_version(entity_type, head_id, from_id)
        to_version = await self._require_version(entity_type, head_id, to_id)
        return _structural_diff(from_version.definition_document, to_version.definition_document)

    async def export_config(
        self, entity_type: ConfigEntityType, head_id: UUID, version_id: UUID | None
    ) -> dict[str, Any]:
        head = await self._require_head(entity_type, head_id)
        target_id = version_id or head.current_version_id
        if target_id is None:
            raise ConfigVersionNotFoundError(entity_type.value, str(head_id), "none")
        version = await self._require_version(entity_type, head_id, target_id)
        return {
            "code": head.code,
            "businessOwner": head.business_owner,
            "definition": version.definition_document,
        }

    async def import_config(
        self,
        entity_type: ConfigEntityType,
        *,
        definition: dict[str, Any],
        actor_id: UUID,
        now: datetime,
    ) -> ConfigVersion:
        code = definition["code"]
        business_owner = definition.get("businessOwner", "imported")
        content = definition["definition"]

        existing = await self._repo.get_head_by_code(entity_type, code)
        if existing is None:
            _head, version = await self.create_draft(
                entity_type,
                code=code,
                business_owner=business_owner,
                definition=content,
                actor_id=actor_id,
                now=now,
            )
            return version
        return await self.create_version_draft(
            entity_type, existing.id, definition=content, actor_id=actor_id, now=now
        )
