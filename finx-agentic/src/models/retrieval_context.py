from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.models._helpers import clean_list


@dataclass(slots=True)
class RetrievalContext:
    tenant_id: str
    user_id: str | None = None
    session_id: str | None = None

    user_groups: list[str] = field(default_factory=list)
    acl_reader_ids: list[str] = field(default_factory=list)
    allowed_spaces: list[str] = field(default_factory=list)
    allowed_projects: list[str] = field(default_factory=list)

    preferred_language: str | None = None

    requested_source_systems: list[str] = field(default_factory=list)
    requested_doc_types: list[str] = field(default_factory=list)
    requested_domains: list[str] = field(default_factory=list)

    metadata_filters: dict[str, Any] = field(default_factory=dict)

    max_context_docs: int = 8
    allow_public_docs: bool = True
    enforce_acl: bool = True
    debug: bool = False

    def __post_init__(self) -> None:
        self.tenant_id = self.tenant_id.strip()
        self.user_id = self.user_id.strip() if self.user_id else None
        self.session_id = self.session_id.strip() if self.session_id else None
        self.preferred_language = (
            self.preferred_language.strip().lower() if self.preferred_language else None
        )

        self.user_groups = clean_list(self.user_groups)
        self.acl_reader_ids = clean_list(self.acl_reader_ids)
        self.allowed_spaces = clean_list(self.allowed_spaces)
        self.allowed_projects = clean_list(self.allowed_projects)
        self.requested_source_systems = [x.lower() for x in clean_list(self.requested_source_systems)]
        self.requested_doc_types = [x.lower() for x in clean_list(self.requested_doc_types)]
        self.requested_domains = [x.lower() for x in clean_list(self.requested_domains)]

        if not self.tenant_id:
            raise ValueError("tenant_id is required")
        if self.max_context_docs <= 0:
            raise ValueError("max_context_docs must be > 0")

    @property
    def effective_reader_ids(self) -> list[str]:
        values: list[str] = []
        if self.user_id:
            values.append(self.user_id)
        values.extend(self.user_groups)
        values.extend(self.acl_reader_ids)
        return clean_list(values)

    def can_access_space(self, space_key: str | None) -> bool:
        if not self.enforce_acl:
            return True
        if not self.allowed_spaces:
            return True
        if not space_key:
            return False
        return space_key in self.allowed_spaces

    def can_access_project(self, project_key: str | None) -> bool:
        if not self.enforce_acl:
            return True
        if not self.allowed_projects:
            return True
        if not project_key:
            return False
        return project_key in self.allowed_projects

    def to_acl_filter(self) -> dict[str, Any]:
        acl_filter: dict[str, Any] = {
            "tenant_id": self.tenant_id,
            "is_deleted": False,
        }

        if self.requested_source_systems:
            acl_filter["source_system"] = {"$in": self.requested_source_systems}

        if self.requested_doc_types:
            acl_filter["doc_type"] = {"$in": self.requested_doc_types}

        if self.requested_domains:
            acl_filter["domains"] = {"$overlap": self.requested_domains}

        if not self.enforce_acl:
            return self.merge_filters(acl_filter)

        acl_conditions: list[dict[str, Any]] = []

        if self.allow_public_docs:
            acl_conditions.append({"is_public": True})

        if self.allowed_spaces:
            acl_conditions.append({"acl_spaces": {"$overlap": self.allowed_spaces}})

        if self.effective_reader_ids:
            acl_conditions.append({"acl_readers": {"$overlap": self.effective_reader_ids}})

        if acl_conditions:
            acl_filter["$or"] = acl_conditions

        return self.merge_filters(acl_filter)

    def merge_filters(self, base_filters: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = dict(base_filters)
        user_extra = extra or self.metadata_filters or {}

        for key, value in user_extra.items():
            if key not in merged:
                merged[key] = value
                continue

            current = merged[key]
            if isinstance(current, dict) and isinstance(value, dict):
                new_dict = dict(current)
                new_dict.update(value)
                merged[key] = new_dict
            else:
                merged[key] = value

        return merged

    def to_dependency_payload(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "user_groups": list(self.user_groups),
            "effective_reader_ids": self.effective_reader_ids,
            "allowed_spaces": list(self.allowed_spaces),
            "allowed_projects": list(self.allowed_projects),
            "preferred_language": self.preferred_language,
            "max_context_docs": self.max_context_docs,
            "allow_public_docs": self.allow_public_docs,
            "enforce_acl": self.enforce_acl,
            "metadata_filters": dict(self.metadata_filters),
            "debug": self.debug,
        }