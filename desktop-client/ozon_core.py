import os
import sys
from typing import Any, Callable, List, Optional

from models import OzonAccount
from services.account_session_service import AccountSessionService
from services.page_service import PageService
from services.session_service import SessionService
from services.constants import TARGET_URL, MENU_BUTTONS
from services.utils import ensure_dirs, read_skus_from_excel, set_logger as set_utils_logger, sleep

if getattr(sys, "frozen", False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(sys._MEIPASS, "ms-playwright")

session_service: Optional[SessionService] = None
page_service: Optional[PageService] = None
sku_service = None
account_session_service: Optional[AccountSessionService] = None


def set_logger(logger_func: Callable[[str], None]):
    global session_service, page_service, sku_service, account_session_service

    set_utils_logger(logger_func)

    session_service = SessionService(logger_func)
    page_service = PageService(logger_func)

    from services.sku_service import SkuService

    sku_service = SkuService(logger_func)
    account_session_service = AccountSessionService(
        logger_func=logger_func,
        session_service=session_service,
        page_service=page_service,
        target_url=TARGET_URL,
        sleep_func=sleep,
    )


def run_account_serialized(email: str, operation: str, action: Callable[[], Any]):
    if not session_service:
        raise RuntimeError("未初始化会话服务，请先调用 set_logger")
    return session_service.run_serialized(email, operation, action)


def ensure_account_session_ready(
    email: str,
    storage_path: str = None,
    headless: bool = False,
    slow_mo: int = 200
):
    """统一准备账号会话，供登录和 SKU 任务共同复用。"""
    if not account_session_service:
        raise RuntimeError("未初始化账号会话服务，请先调用 set_logger")
    account = OzonAccount(email, storage_path)
    return account_session_service.ensure_ready(account, headless=headless, slow_mo=slow_mo)

# slow_mo的意思是：慢动作（slow motion）延迟时间
def prepare_browser(
    email: str,
    storage_path: str = None,
    headless: bool = False,
    slow_mo: int = 200,
):
    """准备浏览器 - 启动浏览器并确保登录状态。"""
    session = ensure_account_session_ready(
        email=email,
        storage_path=storage_path,
        headless=headless,
        slow_mo=slow_mo,
    )
    return session.page


def run_task(
    email: str,
    excel_path: str,
    image_path: str,
    storage_path: str = None,
    headless: bool = False,
    slow_mo: int = 200,
):
    """兼容入口：从 Excel 读取 SKU 后执行任务。"""
    skus = read_skus_from_excel(excel_path)
    return run_task_with_skus(
        email=email,
        skus=skus,
        image_path=image_path,
        storage_path=storage_path,
        headless=headless,
        slow_mo=slow_mo,
    )


def run_task_with_skus(
    email: str,
    skus: List[str],
    image_path: str,
    storage_path: str = None,
    headless: bool = False,
    slow_mo: int = 200,
):
    """执行任务 - 直接使用 SKU 列表发送图片。"""
    ensure_dirs()

    if not os.path.exists(image_path):
        raise FileNotFoundError(f"未找到图片文件: {image_path}")

    normalized_skus = [str(s).strip() for s in skus if str(s).strip()]
    normalized_skus = list(dict.fromkeys(normalized_skus))
    if not normalized_skus:
        raise ValueError("未提供有效 SKU")

    if not account_session_service or not sku_service:
        raise RuntimeError("未初始化核心服务，请先调用 set_logger")

    account = OzonAccount(email, storage_path)
    session = None
    task_page = None

    try:
        session, task_page = account_session_service.acquire_task_page(
            account,
            headless=headless,
            slow_mo=slow_mo,
            operation_name="发送图片任务",
        )
        summary = sku_service.execute(task_page, normalized_skus, image_path, MENU_BUTTONS)
        account_session_service.promote_task_page_if_support(
            session,
            task_page,
            session_id=summary.get("session_id"),
        )
        account_session_service.save_after_task(session, account.storage_path)
        return summary
    finally:
        if task_page is not None:
            account_session_service.release_task_page(session, task_page)


def close_all_sessions():
    """关闭所有浏览器会话。"""
    if session_service:
        session_service.close_all_sessions()


def close_session(email: str):
    """关闭指定邮箱的浏览器会话。"""
    if session_service:
        session_service.close_session(email)
