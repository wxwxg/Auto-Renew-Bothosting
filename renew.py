#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, sys, time, json, requests, subprocess
import urllib.request, urllib.parse, urllib.error
from datetime import datetime
from seleniumbase import SB

# ---------- 全局环境变量配置 ----------
EMAIL         = os.environ.get("EMAIL") or ""           # 单账号邮箱（仅当未使用 ACCOUNTS 时）
SESSION_TOKEN = os.environ.get("SESSION_TOKEN") or ""   # 单账号 session token
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN") or ""   # 单账号 Discord Token
GH_TOKEN      = os.environ.get("GH_TOKEN") or ""        # GitHub PAT token（用于更新 secret）
TG_CHAT_ID    = os.environ.get("TG_CHAT_ID") or ""      # TG chat id
TG_BOT_TOKEN  = os.environ.get("TG_BOT_TOKEN") or ""    # TG bot token
# 注意：以下变量名兼容 ACCOUNTS_JSON 和 ACCOUNTS 两种写法
ACCOUNTS_JSON = os.environ.get("ACCOUNTS_JSON") or os.environ.get("ACCOUNTS") or ""

# ---------- 代理相关（支持 NODE_LINK）----------
IS_PROXY      = os.environ.get("IS_PROXY", "false").lower() == "true"
PROXY_SERVER  = os.environ.get("PROXY_SERVER", "").strip() or "http://127.0.0.1:1080"
NODE_LINK     = os.environ.get("NODE_LINK", "").strip()   # 新增：代理链接（如 vless://, vmess://, socks5:// 等）

# 如果提供了 NODE_LINK，则优先使用它作为代理，并覆盖原有代理设置
if NODE_LINK:
    IS_PROXY = True
    PROXY_SERVER = NODE_LINK
    print(f"🔗 使用 NODE_LINK 代理: {PROXY_SERVER[:50]}...")  # 打印前50字符以免泄露敏感信息
else:
    if IS_PROXY:
        print(f"🔗 使用 PROXY_SERVER 代理: {PROXY_SERVER}")
    else:
        print("🍭 未使用代理，直连访问")

HEADLESS = os.environ.get("HEADLESS", "false").lower() == "true"

# ---------- 工具函数 ----------
def send_telegram_message(message: str):
    """发送 Telegram 通知（全局配置）"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("⚠️ Telegram 未配置，跳过通知")
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message}, timeout=10)
        print("✅ Telegram 通知已发送")
    except Exception as e:
        print(f"❌ Telegram 发送失败: {e}")

def format_notification(status: str, email: str, login_method: str = "SESSION_TOKEN",
                        extra: str = "", error: str = "", expiry_date: str = "") -> str:
    """生成通知文本（含账号邮箱）"""
    local_time = time.gmtime(time.time() + 8 * 3600)
    now = time.strftime("%Y-%m-%d %H:%M:%S", local_time)
    # 对邮箱做脱敏
    if '@' in email:
        name, domain = email.split('@', 1)
        if len(name) > 4:
            masked_email = f"{name[:2]}****{name[-2:]}@{domain}"
        else:
            masked_email = f"{name}@{domain}"
    else:
        masked_email = email[:2] + '****' if len(email) > 4 else email

    lines = [
        "🇫🇮 Bot-hosting 续期通知",
        "",
        f"{status}",
        f"👤 登录账户: {masked_email}",
    ]
    if login_method != "SESSION_TOKEN":
        lines.append(f"🔐 登录方式: {login_method}")
    if expiry_date:
        lines.append(f"📅 到期时间: {expiry_date}")
    if extra:
        lines.append(extra)
    if error:
        lines.append(f"⚠️ 错误信息: {error}")
    lines.append(f"⏱️ 登录时间: {now}")
    return "\n".join(lines)

def get_current_ip(proxy_server: str = "") -> str:
    """获取当前出口 IP（使用 requests，支持代理）"""
    proxies = None
    if proxy_server:
        proxies = {"http": proxy_server, "https": proxy_server}
    response = requests.get("https://api.ip.sb/ip", proxies=proxies, timeout=15)
    response.raise_for_status()
    return response.text.strip()

def format_countdown(countdown_str: str) -> str:
    """格式化倒计时（HH:MM:SS -> 可读）"""
    try:
        h, m, _ = countdown_str.split(':')
        h = int(h)
        m = int(m)
        if h > 0:
            return f"{h}h{m}min"
        else:
            return f"{m}min"
    except:
        return countdown_str

def extract_expiry_date(page_source: str) -> str:
    """从页面源码提取到期日期"""
    patterns = [
        r"[Ee]xpires\s*[:\-]?\s*(\d{4}/\d{2}/\d{2})",
        r"[Ee]xpires\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
        r"(\d{4}/\d{2}/\d{2})\s*[\-–]\s*renew",
        r"(\d{2}/\d{2}/\d{4})\s*[\-–]\s*renew",
        r"(\d{4}/\d{2}/\d{2})\s*[\-–]\s*renew manually to extend for 4 days",
    ]
    for pattern in patterns:
        match = re.search(pattern, page_source)
        if match:
            date_str = match.group(1)
            # MM/DD/YYYY -> YYYY/MM/DD
            if len(date_str.split('/')[-1]) == 4:
                parts = date_str.split('/')
                if len(parts[0]) == 2:
                    return f"{parts[2]}/{parts[0]}/{parts[1]}"
            return date_str
    return None

def get_cookie_info(sb, name):
    """获取指定 Cookie 的值和过期时间"""
    cookies = sb.get_cookies()
    for c in cookies:
        if c.get('name') == name:
            value = c.get('value')
            expiry_ts = c.get('expiry')
            expiry_dt = datetime.fromtimestamp(expiry_ts) if expiry_ts else None
            return value, expiry_dt
    return None, None

def should_update_cookie(new_value, old_value, expiry_dt, days_threshold=3):
    """判断是否需要更新 Cookie"""
    if new_value is None:
        return False
    if new_value != old_value:
        return True
    if expiry_dt:
        remaining = (expiry_dt - datetime.now()).total_seconds()
        if remaining < days_threshold * 24 * 3600:
            return True
    return False

def update_github_secret(secret_name, new_value):
    """通过 gh 命令更新 GitHub Secret"""
    if not new_value:
        print(f"⚠️ 跳过更新 {secret_name}：新值为空")
        return False
    masked = new_value[:4] + "..." + new_value[-4:] if len(new_value) > 8 else "***"
    print(f"🔄 更新 Secret: {secret_name} (新值: {masked})")
    try:
        env = os.environ.copy()
        if GH_TOKEN:
            env["GH_TOKEN"] = GH_TOKEN
        proc = subprocess.run(
            ["gh", "secret", "set", secret_name, "--body", new_value],
            capture_output=True, text=True, timeout=30, check=False,
            env=env
        )
        if proc.returncode == 0:
            return True
        else:
            print(f"❌ 更新失败: {proc.stderr.strip()}")
            return False
    except Exception as e:
        print(f"❌ 异常: {e}")
        return False

def wait_for_turnstile_pass(sb, timeout=30):
    """等待 Turnstile 验证通过"""
    start = time.time()
    cf_indicators = ["verify you are human", "确认您是真人", "troubleshoot", "just a moment"]
    while time.time() - start < timeout:
        page_lower = sb.get_page_source().lower()
        if not any(x in page_lower for x in cf_indicators):
            print("✅ Turnstile 验证已通过")
            return True
        sb.sleep(1)
    print("❌ Turnstile 验证超时未通过")
    return False

# ---------- Discord OAuth 相关函数 ----------
DISCORD_CLIENT_ID   = "884382422530158623"
OAUTH_REDIRECT_URI  = "https://bot-hosting.net/login"
OAUTH_SCOPE         = "identify email guilds"
DISCORD_API         = "https://discord.com/api/v9/oauth2/authorize"
DISCORD_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)
STATE_RE = re.compile(r"[?&]state=([^&]+)")

def capture_discord_state(sb) -> str:
    """从 /login/discord 页面提取 state"""
    print("🔎 获取 Discord OAuth state...")
    sb.uc_open_with_reconnect("https://bot-hosting.net/login/discord", reconnect_time=4)
    time.sleep(2)
    url = sb.get_current_url()
    if "discord.com" not in url:
        print(f"⚠️ 未跳转到 Discord 相关页面，当前 URL：{url}")
        return ""
    m = STATE_RE.search(url)
    if not m:
        print(f"❌ 未能从 URL 中解析出 state，当前 URL：{url}")
        return ""
    state = urllib.parse.unquote(m.group(1))
    print(f"✅ 已捕获 state（当前落地页：{urllib.parse.urlparse(url).path}）")
    return state

def discord_authorize(state: str, discord_token: str) -> str:
    """使用 Discord Token 完成授权，返回回调 URL（代理全局）"""
    query = urllib.parse.urlencode({
        "client_id":     DISCORD_CLIENT_ID,
        "response_type": "code",
        "redirect_uri":  OAUTH_REDIRECT_URI,
        "scope":         OAUTH_SCOPE,
        "state":         state,
    })
    authorize_url = f"{DISCORD_API}?{query}"
    referer = (
        "https://discord.com/oauth2/authorize?" +
        urllib.parse.urlencode({
            "client_id":     DISCORD_CLIENT_ID,
            "redirect_uri":  OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope":         OAUTH_SCOPE,
            "state":         state,
        })
    )
    headers = {
        "accept":           "*/*",
        "authorization":    discord_token,
        "content-type":     "application/json",
        "origin":           "https://discord.com",
        "referer":          referer,
        "user-agent":       DISCORD_UA,
        "x-discord-locale": "zh-CN",
    }
    body = json.dumps({
        "permissions": "0",
        "authorize": True,
        "integration_type": 0,
        "location_context": {
            "guild_id": "10000",
            "channel_id": "10000",
            "channel_type": 10000,
        },
    })
    proxies = None
    if IS_PROXY:
        proxies = {"http": PROXY_SERVER, "https": PROXY_SERVER}
    try:
        resp = requests.post(authorize_url, headers=headers, data=body, proxies=proxies, timeout=20)
        if resp.status_code != 200:
            print(f"❌ Discord OAuth2 授权失败: HTTP {resp.status_code} - {resp.text[:300]}")
            return ""
        resp_data = resp.json()
    except Exception as e:
        print(f"❌ Discord OAuth2 授权异常: {e}")
        return ""
    location = resp_data.get("location", "")
    if not location:
        print(f"❌ 授权响应中未找到 location 字段: {resp_data}")
        return ""
    masked = re.sub(r"code=[^&]+", "code=***", location)
    print(f"✅ 拿到回调 URL: {masked}")
    return location

def do_discord_login(sb, discord_token: str) -> bool:
    """通过 Discord OAuth 登录 bot-hosting.net"""
    print("\n🔑 通过 Discord Token 登录...")
    state = capture_discord_state(sb)
    if not state:
        sb.save_screenshot("login_no_state.png")
        return False
    location = discord_authorize(state, discord_token)
    if not location:
        return False
    print("↩️ 携带授权码打开回调链接...")
    sb.uc_open_with_reconnect(location, reconnect_time=4)
    time.sleep(3)
    url = sb.get_current_url()
    if "/error/banned" in url:
        print("🚫 账号已被封禁")
        sb.save_screenshot("login_banned.png")
        return False
    if "bot-hosting.net" not in url:
        print(f"❌ 回调后未跳转至 bot-hosting.net，当前 URL：{url}")
        sb.save_screenshot("login_no_redirect.png")
        return False
    try:
        body_text = sb.get_text("body")
    except Exception:
        body_text = ""
    if "fraud" in body_text.lower():
        print("🚫 触发风控（fraud attempt），可能是 IP 被拦截")
        sb.save_screenshot("login_fraud.png")
        return False
    for _ in range(30):
        url = sb.get_current_url()
        path = urllib.parse.urlparse(url).path
        if "bot-hosting.net" in url and path != "/login" and not path.startswith("/login/discord"):
            print(f"✅ Discord OAuth 登录成功！当前页面：{url}")
            return True
        time.sleep(0.5)
    print(f"❌ 登录超时或未跳转成功，最终停留在：{url}")
    try:
        body_text = sb.get_text("body")
        print(f"📄 页面正文片段：{body_text[:200].strip()!r}")
    except Exception:
        pass
    sb.save_screenshot("login_timeout.png")
    return False

# ---------- 核心处理函数 ----------
def process_account(account: dict, idx: int):
    """
    处理单个账号的续期流程
    :param account: 包含 email, session_token, discord_token, secret_name(可选) 的字典
    :param idx: 账号索引（用于生成 secret 名称等）
    """
    email = account.get("email", f"账号{idx+1}")
    session_token = account.get("session_token", "")
    discord_token = account.get("discord_token", "")
    secret_name = account.get("secret_name", None)  # 自定义 secret 名

    # 如果没有 token 则跳过
    if not session_token and not discord_token:
        print(f"⚠️ 账号 {email} 既无 SESSION_TOKEN 也无 DISCORD_TOKEN，跳过")
        return

    # 确定 secret 名称（用于更新）
    if not secret_name:
        if idx == 0:
            secret_name = "SESSION_TOKEN"
        else:
            secret_name = f"SESSION_TOKEN_{idx}"

    # 构造浏览器参数（使用全局代理和 Headless）
    sb_kwargs = {"uc": True, "headless": HEADLESS}
    if IS_PROXY:
        print(f"🔗 挂载代理: {PROXY_SERVER[:50]}...")
        sb_kwargs["proxy"] = PROXY_SERVER
    else:
        print("🍭 未使用代理，直连访问")

    login_method = "SESSION_TOKEN"
    with SB(**sb_kwargs) as sb:
        # 打印当前 IP
        try:
            ip = get_current_ip(PROXY_SERVER if IS_PROXY else "")
            print(f"📍 当前出口IP: {ip}")
        except Exception as e:
            print(f"⚠️ 获取出口 IP 失败: {e}")

        login_ok = False

        # 方式1: SESSION_TOKEN Cookie 登录
        if session_token:
            print("🚀 启动浏览器...")
            sb.open("https://bot-hosting.net/")
            sb.wait_for_ready_state_complete()
            sb.sleep(2)

            print("📝 注入 Cookie...")
            cookies = {
                "session_token": session_token,
                "login": "true",
                "theme": "system",
            }
            for name, value in cookies.items():
                if value:
                    sb.add_cookie({"name": name, "value": value, "domain": "bot-hosting.net"})

            print("🌐 访问 https://bot-hosting.net/a/billings ...")
            sb.open("https://bot-hosting.net/a/billings")
            sb.wait_for_ready_state_complete()
            sb.sleep(3)
            current_url = sb.get_current_url()
            current_title = sb.get_title()
            print(f"📝 当前URL: {current_url}, Title: {current_title}")

            if "/a/billings" in current_url and "/login" not in current_url and "error=" not in current_url:
                login_ok = True
                print("✅ SESSION_TOKEN 登录成功, 当前已到达账单页")
            else:
                print(f"❌ SESSION_TOKEN 登录失败，当前URL: {current_url}, 当前标题: {current_title}")

        # 方式2: Discord OAuth 登录（备用）
        if not login_ok and discord_token:
            login_method = "Discord Token"
            print("\n🔄 SESSION_TOKEN 登录失败或未配置，尝试 Discord OAuth 登录...")
            if do_discord_login(sb, discord_token):
                print("🌐 访问 https://bot-hosting.net/a/billings ...")
                sb.open("https://bot-hosting.net/a/billings")
                sb.wait_for_ready_state_complete()
                sb.sleep(3)
                current_url = sb.get_current_url()
                current_title = sb.get_title()
                print(f"📝 当前URL: {current_url}, Title: {current_title}")
                if "a/billings" in current_url:
                    login_ok = True
                    print("✅ Discord OAuth 登录成功,当前已到达账单页")
                else:
                    print(f"❌ Discord OAuth 登录后仍未到达账单页，当前URL: {current_url}")
            else:
                print("❌ Discord OAuth 登录失败")

        if not login_ok:
            error_msg = "Cookie 已失效或页面异常"
            if not session_token and discord_token:
                error_msg = "Discord OAuth 登录失败"
            elif session_token and discord_token:
                error_msg = "SESSION_TOKEN 和 Discord OAuth 均失败"
            send_telegram_message(
                format_notification("❌ 登录失败", email, login_method, error=error_msg)
            )
            return

        # 提取当前到期日期
        sb.sleep(2)
        page_source = sb.get_page_source()
        current_expiry = extract_expiry_date(page_source)
        if current_expiry:
            print(f"📅 当前到期日期: {current_expiry}")
        else:
            print("⚠️ 未能提取当前到期日期")

        # 寻找外部续期按钮
        outer_renew_selector = None
        countdown_text = None
        possible_selectors = [
            'button:contains("Renew")',
            'button:contains("Renew free plan")',
            'a:contains("Renew")',
            '[class*="renew"]',
            '[class*="Renew"]',
        ]
        for selector in possible_selectors:
            try:
                if sb.is_element_visible(selector):
                    button_text = sb.get_text(selector)
                    if "Renew in" in button_text:
                        match = re.search(r"Renew in (\d{2}:\d{2}:\d{2})", button_text)
                        if match:
                            countdown_text = match.group(1)
                        break
                    elif "Renew" in button_text and "in" not in button_text.lower():
                        outer_renew_selector = selector
                        print(f"✅ 续期按钮可用: '{button_text}'")
                        break
            except Exception:
                pass

        # 点击外部续期按钮并处理弹窗
        if outer_renew_selector:
            print("🔄 点击外部续期按钮，等待验证窗口...")
            try:
                sb.sleep(2)
                sb.click(outer_renew_selector)
                sb.sleep(15)
            except Exception as e:
                print(f"❌ 点击外部按钮失败: {e}")
                send_telegram_message(
                    format_notification("❌ 续期失败", email, login_method, error="点击外部续期按钮出错")
                )
                return

            print("🔒 检测弹窗中的 Turnstile 验证...")
            turnstile_passed = False
            for attempt in range(1, 4):
                try:
                    sb.uc_gui_click_captcha()
                    time.sleep(12)
                except Exception as e:
                    print(f"⚠️ 点击 Turnstile 出错: {e}")
                if wait_for_turnstile_pass(sb, timeout=20):
                    turnstile_passed = True
                    break
                else:
                    print(f"⏳ 第 {attempt} 次未通过，重试点击...")

            if not turnstile_passed:
                print("❌ Turnstile 验证最终未通过，脚本退出")
                send_telegram_message(
                    format_notification("❌ 续期失败", email, login_method, error="Turnstile 验证未通过")
                )
                return

            print("⏳ 等待续期按钮可用并点击...")
            time.sleep(5)
            try:
                sb.click('button:contains("Renew for 4 days")', timeout=8)
                print("✅ 已点击续期按钮")
            except Exception as e:
                print(f"续期按钮点击失败: {e}")

            print("⏳ 等待新的过期时间...")
            sb.sleep(6)

            # 提取新的到期日期和倒计时
            new_page_text = sb.get_page_source()
            new_expiry = extract_expiry_date(new_page_text)
            new_match = re.search(r"Renew in (\d{2}:\d{2}:\d{2})", new_page_text)
            if new_match:
                new_countdown = new_match.group(1)
                print(f"✅ 续期成功！新的倒计时: {new_countdown}")
                if new_expiry:
                    print(f"📅 新的到期日期: {new_expiry}")
                send_telegram_message(
                    format_notification(
                        "✅ 续期成功", email, login_method,
                        extra=f"⏱️ 可续期时间: {format_countdown(new_countdown)}后",
                        expiry_date=new_expiry or "（未获取到）"
                    )
                )
            else:
                if new_expiry and new_expiry != current_expiry:
                    print(f"✅ 续期成功，到期日期已更新为: {new_expiry}")
                    send_telegram_message(
                        format_notification(
                            "✅ 续期成功", email, login_method,
                            extra="到期日期已更新",
                            expiry_date=new_expiry
                        )
                    )
                else:
                    print("⚠️ 续期结果未知，到期日期未变化，请手动检查")
                    send_telegram_message(
                        format_notification(
                            "⚠️ 续期可能未成功", email, login_method,
                            extra="请登录后台检查",
                            expiry_date=current_expiry or "（未获取到）"
                        )
                    )
        else:
            if countdown_text:
                friendly = format_countdown(countdown_text)
                print(f"⏳ 未到续期时间，倒计时: {countdown_text} ({friendly})")
                send_telegram_message(
                    format_notification(
                        "⏳ 未到续期时间", email, login_method,
                        extra=f"⏱️ 可续期时间: {friendly}后",
                        expiry_date=current_expiry or "（未获取到）"
                    )
                )
            else:
                print("ℹ️ 未找到续期按钮或倒计时，状态未知")
                send_telegram_message(
                    format_notification(
                        "ℹ️ 无需续期", email, login_method,
                        extra="当前状态未知，请手动检查",
                        expiry_date=current_expiry or "（未获取到）"
                    )
                )

        # 更新 SESSION_TOKEN（如果需要）
        print("🔄 检查 SESSION_TOKEN 是否需要更新")
        new_token, token_expiry = get_cookie_info(sb, "session_token")
        old_token = session_token
        if should_update_cookie(new_token, old_token, token_expiry):
            print("🔄 SESSION_TOKEN 需要更新")
            if GH_TOKEN:
                if update_github_secret(secret_name, new_token):
                    print(f"✅ {secret_name} 更新成功")
                else:
                    print(f"⚠️ 更新 {secret_name} 失败，请检查 GH_TOKEN 权限")
            else:
                print("⚠️ 未设置 GH_TOKEN，无法自动更新")
                print(f"📋 请手动设置 {secret_name} = {new_token[:4]}...{new_token[-4:]}")
        else:
            print("✅ SESSION_TOKEN 无需更新")

        print(f"🏁 账号 {email} 处理完毕")

# ---------- 账号列表构建 ----------
def build_accounts():
    """从环境变量构建账号列表"""
    accounts = []
    # 兼容两种环境变量名：ACCOUNTS_JSON 或 ACCOUNTS
    if ACCOUNTS_JSON:
        try:
            accounts = json.loads(ACCOUNTS_JSON)
            if not isinstance(accounts, list):
                print("⚠️ ACCOUNTS_JSON 不是 JSON 数组，回退到单账号模式")
                accounts = []
            else:
                print(f"✅ 从 ACCOUNTS_JSON 加载了 {len(accounts)} 个账号")
                return accounts
        except json.JSONDecodeError:
            print("⚠️ ACCOUNTS_JSON 解析失败，回退到单账号模式")

    # 单账号模式：从传统环境变量构建
    if SESSION_TOKEN or DISCORD_TOKEN:
        account = {
            "email": EMAIL or "default@example.com",
            "session_token": SESSION_TOKEN,
            "discord_token": DISCORD_TOKEN,
            "secret_name": "SESSION_TOKEN"  # 保持原有 secret 名
        }
        accounts.append(account)
        print("ℹ️ 使用单账号模式（从 EMAIL/SESSION_TOKEN/DISCORD_TOKEN 构建）")
    else:
        print("ℹ️ 未配置任何账号，脚本终止。")
        sys.exit(1)
    return accounts

# ---------- 主函数 ----------
def main():
    print("#" * 25)
    print("   Bot-hosting 自动续期（多账号 + 代理）")
    print("#" * 25)

    accounts = build_accounts()
    if not accounts:
        print("❌ 没有可用的账号，脚本退出。")
        sys.exit(1)

    for idx, acc in enumerate(accounts):
        print(f"\n{'='*30} 处理第 {idx+1}/{len(accounts)} 个账号 {'='*30}")
        process_account(acc, idx)
        # 账号之间适当延迟，避免风控
        if idx < len(accounts) - 1:
            wait_seconds = 30
            print(f"⏳ 等待 {wait_seconds} 秒后处理下一个账号...")
            time.sleep(wait_seconds)

    print("\n✅ 所有账号处理完成。")

if __name__ == "__main__":
    main()
