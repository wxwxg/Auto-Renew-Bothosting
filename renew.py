#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, sys, time, json, requests, subprocess
import urllib.request, urllib.parse, urllib.error
from datetime import datetime
from seleniumbase import SB

# ---------- 环境变量 ----------
EMAIL         = os.environ.get("EMAIL") or ""           
SESSION_TOKEN = os.environ.get("SESSION_TOKEN") or ""   
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN") or ""   
GH_TOKEN      = os.environ.get("GH_TOKEN") or ""        
TG_CHAT_ID    = os.environ.get("TG_CHAT_ID") or ""      
TG_BOT_TOKEN  = os.environ.get("TG_BOT_TOKEN") or ""    
ACCOUNTS_JSON = os.environ.get("ACCOUNTS_JSON") or os.environ.get("ACCOUNTS") or ""

# ---------- 代理 ----------
IS_PROXY      = os.environ.get("IS_PROXY", "false").lower() == "true"
PROXY_SERVER  = os.environ.get("PROXY_SERVER", "").strip() or "http://127.0.0.1:1080"
NODE_LINK     = os.environ.get("NODE_LINK", "").strip()
if NODE_LINK:
    IS_PROXY = True
    PROXY_SERVER = NODE_LINK
    print(f"🔗 使用 NODE_LINK 代理: {PROXY_SERVER[:50]}...")
else:
    if IS_PROXY:
        print(f"🔗 使用 PROXY_SERVER 代理: {PROXY_SERVER}")
    else:
        print("🍭 未使用代理，直连访问")

HEADLESS = os.environ.get("HEADLESS", "false").lower() == "true"

# ---------- 工具函数 ----------
def send_telegram_message(message: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                      json={"chat_id": TG_CHAT_ID, "text": message}, timeout=10)
        print("✅ Telegram 通知已发送")
    except Exception as e:
        print(f"❌ Telegram 发送失败: {e}")

def format_notification(status, email, login_method="SESSION_TOKEN", extra="", error="", expiry_date=""):
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 28800))
    if '@' in email:
        name, domain = email.split('@', 1)
        masked_email = f"{name[:2]}****{name[-2:]}@{domain}" if len(name)>4 else f"{name}@{domain}"
    else:
        masked_email = email[:2] + '****'
    lines = [
        "🇫🇮 Bot-hosting 续期通知", "", f"{status}",
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

def get_current_ip(proxy_server=""):
    proxies = {"http": proxy_server, "https": proxy_server} if proxy_server else None
    response = requests.get("https://api.ip.sb/ip", proxies=proxies, timeout=15)
    response.raise_for_status()
    return response.text.strip()

def format_countdown(countdown_str):
    try:
        h, m, _ = countdown_str.split(':')
        h, m = int(h), int(m)
        return f"{h}h{m}min" if h > 0 else f"{m}min"
    except:
        return countdown_str

def extract_expiry_date(page_source):
    patterns = [
        r"[Ee]xpires\s*[:\-]?\s*(\d{4}/\d{2}/\d{2})",
        r"[Ee]xpires\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
        r"(\d{4}/\d{2}/\d{2})\s*[\-–]\s*renew",
        r"(\d{2}/\d{2}/\d{4})\s*[\-–]\s*renew",
    ]
    for pattern in patterns:
        match = re.search(pattern, page_source)
        if match:
            date_str = match.group(1)
            if len(date_str.split('/')[-1]) == 4:
                parts = date_str.split('/')
                if len(parts[0]) == 2:
                    return f"{parts[2]}/{parts[0]}/{parts[1]}"
            return date_str
    return None

def get_cookie_info(sb, name):
    for c in sb.get_cookies():
        if c.get('name') == name:
            return c.get('value'), datetime.fromtimestamp(c.get('expiry')) if c.get('expiry') else None
    return None, None

def should_update_cookie(new_value, old_value, expiry_dt, days_threshold=3):
    if not new_value or new_value == old_value:
        return False
    if expiry_dt:
        return (expiry_dt - datetime.now()).total_seconds() < days_threshold * 86400
    return True

def update_github_secret(secret_name, new_value):
    if not new_value:
        print("⚠️ 跳过更新：新值为空")
        return False
    masked = new_value[:4] + "..." + new_value[-4:] if len(new_value) > 8 else "***"
    print(f"🔄 更新 Secret: {secret_name} (新值: {masked})")
    try:
        env = os.environ.copy()
        if GH_TOKEN:
            env["GH_TOKEN"] = GH_TOKEN
        proc = subprocess.run(
            ["gh", "secret", "set", secret_name, "--body", new_value],
            capture_output=True, text=True, timeout=30, check=False, env=env
        )
        if proc.returncode == 0:
            return True
        else:
            print(f"❌ 更新失败: {proc.stderr.strip()}")
            return False
    except Exception as e:
        print(f"❌ 异常: {e}")
        return False

# ---------- Discord OAuth (简化) ----------
DISCORD_CLIENT_ID = "884382422530158623"
OAUTH_REDIRECT_URI = "https://bot-hosting.net/login"
OAUTH_SCOPE = "identify email guilds"
DISCORD_API = "https://discord.com/api/v9/oauth2/authorize"
STATE_RE = re.compile(r"[?&]state=([^&]+)")

def capture_discord_state(sb):
    print("🔎 获取 Discord OAuth state...")
    sb.uc_open_with_reconnect("https://bot-hosting.net/login/discord", reconnect_time=4)
    time.sleep(2)
    url = sb.get_current_url()
    if "discord.com" not in url:
        return ""
    m = STATE_RE.search(url)
    if not m:
        return ""
    return urllib.parse.unquote(m.group(1))

def discord_authorize(state, discord_token):
    query = urllib.parse.urlencode({
        "client_id": DISCORD_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": OAUTH_REDIRECT_URI,
        "scope": OAUTH_SCOPE,
        "state": state,
    })
    authorize_url = f"{DISCORD_API}?{query}"
    referer = "https://discord.com/oauth2/authorize?" + urllib.parse.urlencode({
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": OAUTH_SCOPE,
        "state": state,
    })
    headers = {
        "accept": "*/*",
        "authorization": discord_token,
        "content-type": "application/json",
        "origin": "https://discord.com",
        "referer": referer,
        "user-agent": "Mozilla/5.0",
        "x-discord-locale": "zh-CN",
    }
    body = json.dumps({
        "permissions": "0",
        "authorize": True,
        "integration_type": 0,
        "location_context": {"guild_id": "10000", "channel_id": "10000", "channel_type": 10000},
    })
    proxies = {"http": PROXY_SERVER, "https": PROXY_SERVER} if IS_PROXY else None
    try:
        resp = requests.post(authorize_url, headers=headers, data=body, proxies=proxies, timeout=20)
        if resp.status_code != 200:
            return ""
        return resp.json().get("location", "")
    except:
        return ""

def do_discord_login(sb, discord_token):
    print("\n🔑 通过 Discord Token 登录...")
    state = capture_discord_state(sb)
    if not state:
        return False
    location = discord_authorize(state, discord_token)
    if not location:
        return False
    sb.uc_open_with_reconnect(location, reconnect_time=4)
    time.sleep(3)
    if "/error/banned" in sb.get_current_url():
        print("🚫 账号已被封禁")
        return False
    for _ in range(30):
        url = sb.get_current_url()
        if "bot-hosting.net" in url and "/login" not in url and not url.startswith("https://bot-hosting.net/login"):
            return True
        time.sleep(0.5)
    return False

# ---------- 核心处理 ----------
def process_account(account, idx):
    email = account.get("email", f"账号{idx+1}")
    session_token = account.get("session_token", "")
    discord_token = account.get("discord_token", "")
    secret_name = account.get("secret_name", None) or ("SESSION_TOKEN" if idx == 0 else f"SESSION_TOKEN_{idx}")

    if not session_token and not discord_token:
        print(f"⚠️ 账号 {email} 缺少 Token，跳过")
        return

    sb_kwargs = {"uc": True, "headless": HEADLESS}
    if IS_PROXY:
        print(f"🔗 挂载代理: {PROXY_SERVER[:50]}...")
        sb_kwargs["proxy"] = PROXY_SERVER
    else:
        print("🍭 未使用代理，直连访问")

    login_method = "SESSION_TOKEN"
    with SB(**sb_kwargs) as sb:
        try:
            ip = get_current_ip(PROXY_SERVER if IS_PROXY else "")
            print(f"📍 当前出口IP: {ip}")
        except Exception as e:
            print(f"⚠️ 获取出口 IP 失败: {e}")

        # ---------- 登录 ----------
        login_ok = False
        if session_token:
            print("🚀 启动浏览器...")
            sb.open("https://bot-hosting.net/")
            sb.wait_for_ready_state_complete()
            sb.sleep(2)
            print("📝 注入 Cookie...")
            for name, value in {"session_token": session_token, "login": "true", "theme": "system"}.items():
                if value:
                    sb.add_cookie({"name": name, "value": value, "domain": "bot-hosting.net"})
            print("🌐 访问 https://bot-hosting.net/a/billings ...")
            sb.open("https://bot-hosting.net/a/billings")
            sb.wait_for_ready_state_complete()
            sb.sleep(3)
            current_url = sb.get_current_url()
            if "/a/billings" in current_url and "/login" not in current_url:
                login_ok = True
                print("✅ SESSION_TOKEN 登录成功")
            else:
                print(f"❌ SESSION_TOKEN 登录失败，当前URL: {current_url}")

        if not login_ok and discord_token:
            login_method = "Discord Token"
            print("\n🔄 尝试 Discord OAuth 登录...")
            if do_discord_login(sb, discord_token):
                print("🌐 访问 https://bot-hosting.net/a/billings ...")
                sb.open("https://bot-hosting.net/a/billings")
                sb.wait_for_ready_state_complete()
                sb.sleep(3)
                if "/a/billings" in sb.get_current_url():
                    login_ok = True
                    print("✅ Discord OAuth 登录成功")
                else:
                    print("❌ Discord OAuth 后未到达账单页")

        if not login_ok:
            send_telegram_message(format_notification("❌ 登录失败", email, login_method, error="登录失败"))
            return

        # ---------- 获取当前到期日期 ----------
        sb.sleep(2)
        page_source = sb.get_page_source()
        current_expiry = extract_expiry_date(page_source)
        if current_expiry:
            print(f"📅 当前到期日期: {current_expiry}")
        else:
            print("⚠️ 未能提取当前到期日期")

        # ---------- 查找外部续期按钮 ----------
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
            except:
                pass

        if not outer_renew_selector:
            if countdown_text:
                friendly = format_countdown(countdown_text)
                print(f"⏳ 未到续期时间，倒计时: {countdown_text} ({friendly})")
                send_telegram_message(
                    format_notification("⏳ 未到续期时间", email, login_method,
                                       extra=f"⏱️ 可续期时间: {friendly}后",
                                       expiry_date=current_expiry or "（未获取到）")
                )
            else:
                print("ℹ️ 未找到续期按钮或倒计时，状态未知")
                send_telegram_message(format_notification("ℹ️ 无需续期", email, login_method, extra="状态未知，请手动检查"))
            # 仍更新 token
            new_token, _ = get_cookie_info(sb, "session_token")
            if new_token and new_token != session_token and GH_TOKEN:
                update_github_secret(secret_name, new_token)
            print(f"🏁 账号 {email} 处理完毕")
            return

        # ---------- 执行续期 ----------
        renew_success = False
        for attempt in range(1, 3):
            if renew_success:
                break
            print(f"🔄 续期尝试 {attempt}/2")
            try:
                # 点击外部续期按钮
                print("🔄 点击外部续期按钮，等待验证窗口...")
                sb.click(outer_renew_selector)
                sb.sleep(5)

                # ---------- Turnstile 处理 ----------
                print("🔒 处理 Turnstile 验证...")
                try:
                    sb.uc_click_captcha()  # 无头模式兼容
                    print("✅ Turnstile 点击已触发")
                except Exception as e:
                    print(f"⚠️ Turnstile 点击异常: {e}")

                # 等待模态框内续期按钮出现
                renew_button_selector = 'button:contains("Renew for 4 days")'
                button_found = False
                for wait_sec in range(40):
                    try:
                        if sb.is_element_visible(renew_button_selector, timeout=1):
                            button_found = True
                            print("✅ 续期按钮已出现，验证通过")
                            break
                    except:
                        pass
                    # 每 8 秒重试点击 Turnstile
                    if wait_sec % 8 == 0 and wait_sec > 0:
                        try:
                            sb.uc_click_captcha()
                        except:
                            pass
                    time.sleep(1)

                if not button_found:
                    print("❌ 续期按钮未出现，Turnstile 验证失败")
                    # 关闭模态框
                    sb.driver.execute_script("""
                        var modal = document.querySelector('.modal, .overlay, [role="dialog"]');
                        if (modal) modal.style.display = 'none';
                    """)
                    sb.sleep(2)
                    continue

                # 点击续期按钮
                print("⏳ 点击续期按钮...")
                sb.click(renew_button_selector, timeout=5)
                print("✅ 已点击续期按钮")

                # 等待处理完成
                print("⏳ 等待续期完成...")
                sb.sleep(20)

                # 刷新页面获取最新状态
                sb.open("https://bot-hosting.net/a/billings")
                sb.wait_for_ready_state_complete()
                sb.sleep(8)

                new_page_text = sb.get_page_source()
                new_expiry = extract_expiry_date(new_page_text)
                new_match = re.search(r"Renew in (\d{2}:\d{2}:\d{2})", new_page_text)

                if new_expiry and new_expiry != current_expiry:
                    print(f"✅ 续期成功！到期日期已更新为: {new_expiry}")
                    send_telegram_message(
                        format_notification("✅ 续期成功", email, login_method, extra="到期日期已更新", expiry_date=new_expiry)
                    )
                    renew_success = True
                    break
                elif new_match:
                    new_countdown = new_match.group(1)
                    print(f"✅ 续期成功！新的倒计时: {new_countdown}")
                    send_telegram_message(
                        format_notification(
                            "✅ 续期成功", email, login_method,
                            extra=f"⏱️ 可续期时间: {format_countdown(new_countdown)}后",
                            expiry_date=new_expiry or "（未获取到）"
                        )
                    )
                    renew_success = True
                    break
                else:
                    print("⚠️ 续期结果未知，到期日期未变化")
                    # 再次刷新
                    sb.sleep(5)
                    sb.open("https://bot-hosting.net/a/billings")
                    sb.wait_for_ready_state_complete()
                    sb.sleep(3)
                    new_page_text = sb.get_page_source()
                    new_expiry = extract_expiry_date(new_page_text)
                    if new_expiry and new_expiry != current_expiry:
                        print(f"✅ 续期成功（延迟），到期日期已更新为: {new_expiry}")
                        send_telegram_message(
                            format_notification("✅ 续期成功", email, login_method, extra="到期日期已更新", expiry_date=new_expiry)
                        )
                        renew_success = True
                        break
                    else:
                        print("❌ 续期失败，准备重试")
                        try:
                            sb.driver.execute_script("""
                                var modal = document.querySelector('.modal, .overlay, [role="dialog"]');
                                if (modal) modal.style.display = 'none';
                            """)
                        except:
                            pass
                        sb.sleep(2)
                        continue
            except Exception as e:
                print(f"⚠️ 续期流程异常: {e}")
                try:
                    sb.open("https://bot-hosting.net/a/billings")
                    sb.wait_for_ready_state_complete()
                    sb.sleep(3)
                except:
                    pass
                continue

        if not renew_success:
            print("❌ 所有续期尝试均失败，请手动检查")
            send_telegram_message(format_notification("❌ 续期失败", email, login_method, error="多次尝试后仍未成功"))

        # ---------- 更新 SESSION_TOKEN ----------
        print("🔄 检查 SESSION_TOKEN 是否需要更新")
        new_token, token_expiry = get_cookie_info(sb, "session_token")
        if should_update_cookie(new_token, session_token, token_expiry):
            if GH_TOKEN:
                if update_github_secret(secret_name, new_token):
                    print(f"✅ {secret_name} 更新成功")
                else:
                    print(f"⚠️ 更新 {secret_name} 失败")
            else:
                print("⚠️ 未设置 GH_TOKEN，无法自动更新")
                print(f"📋 请手动设置 {secret_name} = {new_token[:4]}...{new_token[-4:]}")
        else:
            print("✅ SESSION_TOKEN 无需更新")

        print(f"🏁 账号 {email} 处理完毕")

# ---------- 账号构建 ----------
def build_accounts():
    accounts = []
    if ACCOUNTS_JSON:
        try:
            accounts = json.loads(ACCOUNTS_JSON)
            if isinstance(accounts, list):
                print(f"✅ 从 ACCOUNTS_JSON 加载了 {len(accounts)} 个账号")
                return accounts
        except:
            print("⚠️ ACCOUNTS_JSON 解析失败，回退到单账号模式")
    if SESSION_TOKEN or DISCORD_TOKEN:
        accounts.append({
            "email": EMAIL or "default@example.com",
            "session_token": SESSION_TOKEN,
            "discord_token": DISCORD_TOKEN,
            "secret_name": "SESSION_TOKEN"
        })
        print("ℹ️ 使用单账号模式")
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
        if idx < len(accounts) - 1:
            print("⏳ 等待 30 秒后处理下一个账号...")
            time.sleep(30)

    print("\n✅ 所有账号处理完成。")

if __name__ == "__main__":
    main()
