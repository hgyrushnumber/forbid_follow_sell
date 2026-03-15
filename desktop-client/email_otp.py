import imaplib
import email
import email.header
import re
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup

# 默认配置（保持向后兼容）
EMAIL_ADDR = "xpw709@163.com"
EMAIL_PASS = "UE4NLW7W2X4NzunU"   # 163 邮箱授权码
IMAP_SERVER = "imap.163.com"

OZON_MAIL_FROM = "mailer@sender.ozon.ru"
OZON_MAIL_SUBJECT_KEYWORD = "Подтверждение учетных данных Ozon"


def get_imap_server(email_account):
    """根据邮箱域名获取对应的IMAP服务器"""
    email_domain = email_account.split("@")[1].lower()

    if email_domain == "163.com":
        return "imap.163.com"
    elif email_domain == "qq.com":
        return "imap.qq.com"
    elif email_domain == "gmail.com":
        return "imap.gmail.com"
    elif email_domain in ["outlook.com", "hotmail.com"]:
        return "imap-mail.outlook.com"
    elif email_domain == "126.com":
        return "imap.126.com"
    elif email_domain == "yeah.net":
        return "imap.yeah.net"
    elif email_domain == "sina.com":
        return "imap.sina.com"
    else:
        print(f"⚠️ 未知邮箱域名 {email_domain}，使用默认IMAP服务器: {IMAP_SERVER}")
        return IMAP_SERVER


def decode_mime_header(value: str) -> str:
    if not value:
        return ""

    parts = email.header.decode_header(value)
    decoded = []

    for text, charset in parts:
        if isinstance(text, bytes):
            try:
                decoded.append(text.decode(charset or "utf-8", errors="ignore"))
            except Exception:
                try:
                    decoded.append(text.decode("utf-8", errors="ignore"))
                except Exception:
                    decoded.append(text.decode("cp1251", errors="ignore"))
        else:
            decoded.append(text)

    return "".join(decoded)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def extract_text_from_email(msg):
    plain_parts = []
    html_parts = []
    raw_html_parts = []

    if msg.is_multipart():
        parts = msg.walk()
    else:
        parts = [msg]

    for part in parts:
        content_type = part.get_content_type()
        content_disposition = str(part.get("Content-Disposition", ""))

        if "attachment" in content_disposition.lower():
            continue

        if content_type not in ["text/plain", "text/html"]:
            continue

        payload = part.get_payload(decode=True)
        if not payload:
            continue

        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="ignore")
        except Exception:
            try:
                text = payload.decode("utf-8", errors="ignore")
            except Exception:
                text = payload.decode("cp1251", errors="ignore")

        if content_type == "text/plain":
            plain_parts.append(text)
        elif content_type == "text/html":
            raw_html_parts.append(text)
            html_parts.append(html_to_text(text))

    plain_text = "\n".join(plain_parts)
    html_text = "\n".join(html_parts)
    raw_html = "\n".join(raw_html_parts)

    return plain_text, html_text, raw_html


def send_imap_id(mail: imaplib.IMAP4_SSL):
    try:
        typ, data = mail.xatom(
            "ID",
            '("name" "python-imap-ozon" "version" "1.0.0" "vendor" "custom-script" "support-email" "xpw709@163.com")'
        )
        print(f"ID 命令返回: {typ}, {data}")
        return typ == "OK"
    except Exception as e:
        print(f"⚠️ 发送 IMAP ID 失败: {e}")
        return False


def extract_otp_from_text(text: str):
    if not text:
        return None

    normalized = re.sub(r"\s+", " ", text).strip()

    context_patterns = [
        r"используйте код[:\s]*([0-9]{6})",
        r"код[:\s]*([0-9]{6})",
        r"verification code[:\s]*([0-9]{6})",
        r"confirmation code[:\s]*([0-9]{6})",
    ]

    for pattern in context_patterns:
        m = re.search(pattern, normalized, flags=re.IGNORECASE)
        if m:
            return m.group(1)

    all_codes = re.findall(r"\b([0-9]{6})\b", normalized)
    if all_codes:
        seen = set()
        unique_codes = []
        for c in all_codes:
            if c not in seen:
                seen.add(c)
                unique_codes.append(c)
        print(f"检测到的所有 6 位数字: {unique_codes}")
        return unique_codes[-1]

    return None


def parse_email_datetime(date_str: str):
    try:
        dt = parsedate_to_datetime(date_str)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def is_fresh_email_by_time(email_dt, request_time, tolerance_seconds=15):
    """
    只接受 request_time 之后的新邮件。
    加少量容错，避免服务器时间和本机时间有轻微偏差。
    """
    if request_time is None or email_dt is None:
        return True

    threshold = request_time - timedelta(seconds=tolerance_seconds)
    return email_dt >= threshold


def safe_decode_mail_id(mail_id):
    try:
        if isinstance(mail_id, bytes):
            return int(mail_id.decode())
        return int(mail_id)
    except Exception:
        return None


def get_latest_ozon_mail_id(email_account=EMAIL_ADDR, email_password=EMAIL_PASS):
    """
    获取当前邮箱里最新一封 Ozon 验证码邮件的 ID。
    用于主流程在“点击提交邮箱”之前建立基线。
    """
    imap_server = get_imap_server(email_account)
    print(f"正在获取当前最新 Ozon 验证码邮件 ID... (服务器: {imap_server})")

    mail = None
    try:
        mail = imaplib.IMAP4_SSL(imap_server, 993)
        mail.login(email_account, email_password)
        print("✅ 邮箱登录成功")

        send_imap_id(mail)

        select_status, select_data = mail.select()
        print(f"SELECT 状态: {select_status}, 数据: {select_data}")
        if select_status != "OK":
            print("⚠️ 无法打开邮箱目录，返回 None")
            return None

        search_status, data = mail.search(None, "ALL")
        print(f"SEARCH 状态: {search_status}")
        if search_status != "OK":
            print("⚠️ 获取邮件列表失败，返回 None")
            return None

        ids = data[0].split()
        if not ids:
            print("⚠️ 邮箱没有邮件")
            return None

        recent_ids = ids[-50:]

        for mail_id in reversed(recent_ids):
            fetch_status, msg_data = mail.fetch(mail_id, "(RFC822)")
            if fetch_status != "OK":
                continue

            for response_part in msg_data:
                if not isinstance(response_part, tuple):
                    continue

                msg = email.message_from_bytes(response_part[1])

                subject = decode_mime_header(msg.get("Subject", ""))
                from_addr = decode_mime_header(msg.get("From", ""))

                if OZON_MAIL_FROM in from_addr and OZON_MAIL_SUBJECT_KEYWORD in subject:
                    latest_id = safe_decode_mail_id(mail_id)
                    print(f"✅ 当前最新 Ozon 验证码邮件 ID: {latest_id}")
                    return latest_id

        print("ℹ️ 当前没有找到历史 Ozon 验证码邮件")
        return None

    except Exception as e:
        print(f"❌ 获取最新 Ozon 邮件 ID 失败: {e}")
        return None

    finally:
        if mail is not None:
            try:
                mail.logout()
            except Exception:
                pass


def get_otp_from_email(request_time=None, min_mail_id=None, max_wait_seconds=60,
                      email_account=EMAIL_ADDR, email_password=EMAIL_PASS):
    """
    双保险:
    1. 只接受 request_time 之后的新邮件
    2. 只接受 mail_id > min_mail_id 的新邮件
    """
    imap_server = get_imap_server(email_account)
    print(f"正在连接邮箱 {imap_server} 查找 Ozon 验证码...")

    if request_time is not None:
        print(f"仅接受这个时间之后的新邮件: {request_time.isoformat()}")

    if min_mail_id is not None:
        print(f"仅接受这个邮件 ID 之后的新邮件: {min_mail_id}")

    mail = None
    try:
        mail = imaplib.IMAP4_SSL(imap_server, 993)
        mail.login(email_account, email_password)
        print("✅ 邮箱登录成功")

        try:
            cap_status, caps = mail.capability()
            print(f"CAPABILITY: {cap_status}, {caps}")
        except Exception as e:
            print(f"⚠️ 获取 CAPABILITY 失败: {e}")

        send_imap_id(mail)

        loop_count = max_wait_seconds // 5
        for i in range(loop_count):
            select_status, select_data = mail.select()
            print(f"第 {i + 1} 次检查，SELECT 状态: {select_status}, 数据: {select_data}")

            if select_status != "OK":
                print("❌ 无法打开邮箱目录")
                return None

            search_status, data = mail.search(None, "ALL")
            print(f"SEARCH 状态: {search_status}")

            if search_status != "OK":
                print("⚠️ 获取邮件列表失败，5 秒后重试...\n")
                time.sleep(5)
                continue

            ids = data[0].split()
            if not ids:
                print("⚠️ 邮箱没有邮件，5 秒后重试...\n")
                time.sleep(5)
                continue

            recent_ids = ids[-30:]
            print(f"准备扫描最近 {len(recent_ids)} 封邮件")

            for mail_id in reversed(recent_ids):
                numeric_mail_id = safe_decode_mail_id(mail_id)

                # 先用 ID 过滤旧邮件
                if min_mail_id is not None and numeric_mail_id is not None and numeric_mail_id <= min_mail_id:
                    continue

                fetch_status, msg_data = mail.fetch(mail_id, "(RFC822)")
                if fetch_status != "OK":
                    continue

                for response_part in msg_data:
                    if not isinstance(response_part, tuple):
                        continue

                    msg = email.message_from_bytes(response_part[1])

                    subject = decode_mime_header(msg.get("Subject", ""))
                    from_addr = decode_mime_header(msg.get("From", ""))
                    date_str = decode_mime_header(msg.get("Date", ""))
                    email_dt = parse_email_datetime(date_str)

                    print("-" * 60)
                    print("ID:", numeric_mail_id)
                    print("From:", from_addr)
                    print("Subject:", subject)
                    print("Date:", date_str)
                    print("Parsed UTC Date:", email_dt.isoformat() if email_dt else "None")

                    if OZON_MAIL_FROM not in from_addr:
                        continue

                    if OZON_MAIL_SUBJECT_KEYWORD not in subject:
                        continue

                    if not is_fresh_email_by_time(email_dt, request_time):
                        print("⚠️ 这是一封旧验证码邮件（时间过滤），跳过")
                        continue

                    plain_text, html_text, raw_html = extract_text_from_email(msg)

                    otp = extract_otp_from_text(html_text)
                    if not otp:
                        otp = extract_otp_from_text(plain_text)
                    if not otp:
                        otp = extract_otp_from_text(raw_html)

                    if otp:
                        print(f"✅ 找到新验证码: {otp}")
                        return {
                            "otp": otp,
                            "mail_id": numeric_mail_id,
                            "email_dt": email_dt.isoformat() if email_dt else None,
                            "subject": subject,
                            "from_addr": from_addr,
                        }

            print("⏳ 本轮未找到新验证码邮件，5 秒后重试...\n")
            time.sleep(5)

    except Exception as e:
        print(f"❌ 邮箱读取失败: {e}")

    finally:
        if mail is not None:
            try:
                mail.logout()
            except Exception:
                pass

    return None