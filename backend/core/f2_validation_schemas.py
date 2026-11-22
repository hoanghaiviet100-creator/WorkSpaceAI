"""Internal Q05 receipts. Only the validation service may supply these as truth.

VERIFIED means extractive correspondence to the selected source snapshot, not
external factual accuracy. Original Q01 SourceRefs always remain UNVERIFIED.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr

from backend.core.f2_study_schemas import StudyFormat


class _ValidationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class StudyValidationIssue(_ValidationModel):
    code: StrictStr
    message: StrictStr
    severity: Literal["REVIEW_REQUIRED", "REJECTED"]


class StudyItemValidation(_ValidationModel):
    item_id: StrictStr
    source_status: Literal["MATCHED", "FAILED", "NOT_CHECKED"]
    support_status: Literal["SUPPORTED", "REVIEW_REQUIRED", "REJECTED", "NOT_CHECKED"]
    issues: tuple[StudyValidationIssue, ...] = ()


class StudyValidationResult(_ValidationModel):
    workspace_id: StrictStr
    study_format: StudyFormat
    resource_id: StrictStr | None = None
    resource_digest: StrictStr | None = None
    source_snapshot_digest: StrictStr | None = None
    method: Literal["EXTRACTIVE_DEFINITION_V1", "EXTRACTIVE_STUDY_V2"] = "EXTRACTIVE_DEFINITION_V1"
    structure_status: Literal["VALID", "INVALID"]
    items: tuple[StudyItemValidation, ...] = ()
    issues: tuple[StudyValidationIssue, ...] = ()

    @property
    def status(self) -> Literal["VERIFIED", "REVIEW_REQUIRED", "REJECTED"]:
        if (self.structure_status == "INVALID"
            or any(issue.severity == "REJECTED" for issue in self.issues)
            or any(item.source_status == "FAILED" or item.support_status == "REJECTED"
                   or any(issue.severity == "REJECTED" for issue in item.issues)
                   for item in self.items)):
            return "REJECTED"
        if (not self.items or not self.resource_id or not self.resource_digest
            or not self.source_snapshot_digest or self.issues
            or any(item.source_status != "MATCHED" or item.support_status != "SUPPORTED"
                   or item.issues for item in self.items)):
            return "REVIEW_REQUIRED"
        return "VERIFIED"

    @property
    def release_ready(self) -> bool:
        return self.status == "VERIFIED"

    @property
    def message(self) -> str:
        if self.release_ready:
            if self.method == "EXTRACTIVE_STUDY_V2":
                return "Đã đối chiếu cấu trúc, trích dẫn và đáp án bằng mẫu nguyên văn với nguồn hiện tại."
            return "Đã đối chiếu cấu trúc, trích dẫn và đáp án định nghĩa với nguồn hiện tại."
        if self.status == "REJECTED":
            return "Học liệu chưa được phép sử dụng. Hãy kiểm tra lỗi và tạo lại từ nguồn hợp lệ."
        return "Chưa đủ bằng chứng để xác minh tự động. Cần review hoặc tạo lại học liệu."
