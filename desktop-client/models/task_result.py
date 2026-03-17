from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SkuProcessResult:
    """
    单个 SKU 的处理结果。
    后面你如果要做更清晰的“接口判定 / 状态回传”，这个结构会很好用。
    """

    sku: str
    success: bool = False
    stage: str = "init"   # init / search / upload / submit / finish / failed
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sku": self.sku,
            "success": self.success,
            "stage": self.stage,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class TaskResult:
    """
    整批任务结果。
    """

    success: bool = False
    message: str = ""
    stage: str = "init"
    account_email: str = ""
    total_skus: int = 0
    success_count: int = 0
    failed_count: int = 0
    processed_skus: List[SkuProcessResult] = field(default_factory=list)
    error: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def add_sku_result(self, result: SkuProcessResult) -> None:
        self.processed_skus.append(result)
        self.total_skus += 1
        if result.success:
            self.success_count += 1
        else:
            self.failed_count += 1

    def finalize(self) -> None:
        self.success = self.failed_count == 0 and self.total_skus > 0
        if self.success:
            self.stage = "finish"
            if not self.message:
                self.message = f"任务完成，共处理 {self.total_skus} 个 SKU"
        else:
            if self.failed_count > 0:
                self.stage = "failed"
                if not self.message:
                    self.message = (
                        f"任务部分失败，成功 {self.success_count} 个，失败 {self.failed_count} 个"
                    )

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "stage": self.stage,
            "account_email": self.account_email,
            "total_skus": self.total_skus,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "processed_skus": [item.to_dict() for item in self.processed_skus],
            "error": self.error,
            "details": self.details,
        }