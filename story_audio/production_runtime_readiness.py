"""Safe production-runtime readiness projection for the daily-use UI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .batch_prepare_runtime_integration import PRODUCTION, RuntimeIntegrationDescriptor, public_runtime_readiness
from .runtime_operator_session import RuntimeOperatorSession


_BLOCKERS = {
    "RUNTIME_NOT_PRODUCTION": "Ứng dụng chưa chạy bằng môi trường sản xuất chuẩn.",
    "SUPERVISED_LAUNCHER_REQUIRED": "Cần khởi động lại bằng launcher sản xuất chuẩn.",
    "AUTH_CONFIGURATION_INVALID": "Cấu hình xác thực vận hành chưa hợp lệ.",
    "AUTH_BOOTSTRAP_MISSING": "Launcher chưa cấp phiên vận hành cho ứng dụng.",
    "AUTH_BOOTSTRAP_MISMATCH": "Phiên vận hành không khớp với cấu hình xác thực.",
    "CANONICAL_DB_INVALID": "Không xác nhận được cơ sở dữ liệu production chuẩn.",
    "OUTPUT_ROOT_NOT_WRITABLE": "Thư mục xuất audio chưa sẵn sàng để ghi.",
    "PREPARE_DISABLED": "PREPARE đang được khóa trong cấu hình vận hành.",
    "KILL_SWITCH_ACTIVE": "Kill switch đang chặn thao tác sản xuất.",
    "SCHEMA_NOT_READY": "Schema hiện tại chưa sẵn sàng cho PREPARE.",
    "OPERATOR_WINDOW_CLOSED": "Cửa sổ thao tác sản xuất hiện đang đóng.",
    "PROVIDER_NOT_READY": "Dịch vụ tạo audio chưa sẵn sàng.",
    "START_RENDER_DISABLED": "Quyền bắt đầu tạo audio chưa được mở.",
}


def _output_root_writable(path: Path) -> bool:
    try:
        return path.is_dir() and os.access(path, os.W_OK)
    except OSError:
        return False


def _append(blockers: list[str], code: str, when: bool) -> None:
    if when and code not in blockers:
        blockers.append(code)


def production_runtime_readiness(
    descriptor: RuntimeIntegrationDescriptor,
    *,
    session: RuntimeOperatorSession,
    output_root: Path,
    provider_configured: bool,
    mutation_service_constructed: bool,
) -> dict[str, Any]:
    """Return UI-safe state only; no token, hash, path, or internal reason leaks."""

    legacy = public_runtime_readiness(descriptor)
    canonical_db_path_valid = bool(
        descriptor.canonical_backed
        and descriptor.schema_version == descriptor.required_schema_version
        and descriptor.quick_check == "ok"
    )
    output_root_writable = _output_root_writable(output_root)
    authentication_configured = descriptor.authentication_state == "AUTH_CONFIGURED"
    authentication_verified = bool(session.verified)
    blockers: list[str] = []
    _append(blockers, "RUNTIME_NOT_PRODUCTION", descriptor.runtime_mode != PRODUCTION)
    _append(blockers, session.blocker_code or "AUTH_BOOTSTRAP_MISSING", not authentication_verified)
    _append(blockers, "CANONICAL_DB_INVALID", not canonical_db_path_valid)
    _append(blockers, "OUTPUT_ROOT_NOT_WRITABLE", not output_root_writable)
    _append(blockers, "SCHEMA_NOT_READY", descriptor.schema_version != descriptor.required_schema_version)
    _append(blockers, "KILL_SWITCH_ACTIVE", descriptor.kill_switch_active)
    _append(blockers, "PREPARE_DISABLED", not descriptor.feature_available or not descriptor.mutation_enabled)
    _append(blockers, "OPERATOR_WINDOW_CLOSED", not descriptor.operator_window_open)
    _append(blockers, "AUTH_CONFIGURATION_INVALID", not authentication_configured)
    prepare_allowed = bool(
        descriptor.prepare_mutation_enabled
        and mutation_service_constructed
        and authentication_verified
        and canonical_db_path_valid
        and output_root_writable
    )
    start_render_allowed = bool(prepare_allowed and descriptor.production_render_enabled and provider_configured)
    start_blockers = list(blockers)
    _append(start_blockers, "PROVIDER_NOT_READY", not provider_configured)
    _append(start_blockers, "START_RENDER_DISABLED", not descriptor.production_render_enabled)
    return {
        **legacy,
        "schema": "story-audio-production-runtime-readiness/v1",
        "runtime_mode_label": "Sản xuất" if descriptor.runtime_mode == PRODUCTION else "Chỉ đọc",
        "operator_authentication_configured": authentication_configured,
        "operator_authentication_verified": authentication_verified,
        "canonical_db_path_valid": canonical_db_path_valid,
        "output_root_writable": output_root_writable,
        "required_secrets_present": authentication_configured and authentication_verified,
        "provider_configuration_present": bool(provider_configured),
        "mutation_service_constructed": bool(mutation_service_constructed),
        "mutation_route_registered": bool(mutation_service_constructed),
        "prepare_allowed": prepare_allowed,
        "start_render_allowed": start_render_allowed,
        "mutation_authorized": prepare_allowed,
        "start_render_available": start_render_allowed,
        "authentication_state": "READY" if authentication_verified else "NOT_READY",
        "blocker_codes": blockers,
        "blockers": [{"code": code, "message": _BLOCKERS[code]} for code in blockers],
        "start_render_blocker_codes": start_blockers,
        "start_render_blockers": [
            {"code": code, "message": _BLOCKERS[code]} for code in start_blockers
        ],
    }


__all__ = ["production_runtime_readiness"]
