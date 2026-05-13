import os
import json
import requests
import smtplib
import datetime
import socket
import logging
import sys
from email.message import EmailMessage
import subprocess
import re        
import ipaddress 
import time
from generators.email_content_generator import create_alarm_email

# =====================
# 智慧路徑設定 (讓 PyInstaller 能找到檔案)
# =====================
if getattr(sys, 'frozen', False):
    # 如果是 .exe 執行檔，取得 exe 所在的目錄
    base_path = os.path.dirname(sys.executable)
else:
    # 如果是 .py 腳本，取得腳本所在的目錄
    base_path = os.path.dirname(os.path.abspath(__file__))

# 組合成 config.json 的絕對路徑
config_path = os.path.join(base_path, "config.json")

# =====================
# 讀取 config 設定檔
# =====================
with open(config_path, encoding="utf-8-sig") as f:
    config = json.load(f)

# =====================
# 設定 log
# =====================
today = datetime.date.today().strftime("%Y-%m-%d")
os.makedirs("logs", exist_ok=True)
log_file = f"logs/logs_{today}.log"
error_file = f"logs/error_{today}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

error_handler = logging.FileHandler(error_file, encoding="utf-8")
error_handler.setLevel(logging.ERROR)
logging.getLogger().addHandler(error_handler)


# =====================
# 輔助函式
# =====================
def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def clean_old_files(folder, prefix, days):
    deleted_files = []
    if not os.path.exists(folder):
        return deleted_files
    
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    for f in os.listdir(folder):
        if f.startswith(prefix):
            full_path = os.path.join(folder, f)
            if os.path.isfile(full_path):
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(full_path))
                if mtime < cutoff:
                    os.remove(full_path)
                    deleted_files.append(full_path)
    return deleted_files

def send_email(subject, html_content, attach_json_path=None):
    try:
        smtp_cfg = config["notification"]["email"]
        if not smtp_cfg["enabled"]:
            logging.info("Email 通知功能已關閉，跳過寄送。")
            return
        
        msg = EmailMessage()
        msg["From"] = smtp_cfg["sender"]
        msg["To"] = ", ".join(smtp_cfg["recipients"])
        msg["Subject"] = subject
        msg.add_header('Content-Type', 'text/html')
        msg.set_payload(html_content, charset="utf-8")

        if attach_json_path and config.get("alerting", {}).get("attach_debug_json_in_email", False):
            with open(attach_json_path, "rb") as f:
                msg.add_attachment(f.read(), maintype="application", subtype="json", filename=os.path.basename(attach_json_path))

        with smtplib.SMTP(smtp_cfg["smtp_server"], smtp_cfg["smtp_port"]) as server:
            server.send_message(msg)
        logging.info(f"Email 通知已成功寄送至: {', '.join(smtp_cfg['recipients'])}")
    except Exception as e:
        logging.error(f"Email 寄送失敗: {e}", exc_info=True)

def send_line_message(content):
    try:
        line_cfg = config["notification"]["line_message"]
        if not line_cfg["enabled"]:
            logging.info("LINE 通知功能已關閉，跳過發送。")
            return
        headers = {"Authorization": f"Bearer {line_cfg['line_message_token']}"}
        payload = {"message": content}
        response = requests.post("https://notify-api.line.me/api/notify", headers=headers, data=payload, timeout=10)
        response.raise_for_status()
        logging.info("LINE Notify 訊息已成功發送。")
    except Exception as e:
        logging.error(f"LINE Notify 發送失敗: {e}", exc_info=True)

def check_reachability(target, timeout_ms, retries=1):
    """
    檢查指定 IP (Ping) 或 Domain (TCP 443) 是否可連線。
    [v3 - Final] 最終修正版，整合語言適應性與更可靠的成功判斷。
    """
    try:
        ipaddress.ip_address(target)
        is_ip = True
    except ValueError:
        is_ip = False

    for attempt in range(retries):
        try:
            if is_ip:
                # --- IP: 使用 Ping ---
                command = ["ping", "-n", "1", "-w", str(timeout_ms), target]
                result = subprocess.run(
                    command, 
                    capture_output=True, 
                    text=True, 
                    check=False,
                    encoding='cp950', 
                    errors='ignore'
                )
                
                # 最終修正：只依賴 returncode == 0 作為成功依據，這是跨語言最可靠的方式。
                if result.returncode == 0:
                    match = re.search(r"(?:Average|平均) = (\d+)ms", result.stdout)
                    latency = match.group(1) + "ms" if match else "0ms" # 若解析不到則給 0ms
                    logging.info(f"健康檢查 (Ping): {target} 成功, 延遲: {latency}")
                    return {"target": target, "status": "✅ OK", "method": "Ping", "latency": latency}
                else:
                    logging.warning(f"健康檢查 (Ping): {target} 失敗 (第 {attempt+1}/{retries} 次), returncode={result.returncode}")
            
            else:
                # --- Domain: 測試 TCP Port 443 (此部分邏輯不變) ---
                start_time = datetime.datetime.now()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout_ms / 1000.0)
                connect_result = sock.connect_ex((target, 443))
                sock.close()
                
                if connect_result == 0:
                    end_time = datetime.datetime.now()
                    latency = f"{(end_time - start_time).total_seconds() * 1000:.0f}ms"
                    logging.info(f"健康檢查 (TCP:443): {target} 成功, 延遲: {latency}")
                    return {"target": target, "status": "✅ OK", "method": "TCP:443", "latency": latency}
                else:
                    logging.warning(f"健康檢查 (TCP:443): {target} 失敗 (第 {attempt+1}/{retries} 次)")

        except Exception as e:
            logging.error(f"健康檢查 {target} 發生例外 (第 {attempt+1}/{retries} 次): {e}")

    # 所有重試都失敗後的回傳
    method = "Ping" if is_ip else "TCP:443"
    return {"target": target, "status": "❌ Fail", "method": method, "latency": "N/A"}

def load_notified_cache():
    path = config["storage"]["cache_notified_path"]
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_notified_cache(cache_set):
    path = config["storage"]["cache_notified_path"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(list(cache_set), f, ensure_ascii=False, indent=2)

def load_system_status():
    """讀取系統狀態檔案 (包含連續失敗次數)"""
    path = config["alerting"]["consecutive_failures_alert"]["status_file_path"]
    # 預設狀態，確保所有鍵都存在
    default_status = {"connect_timeout_failures": 0, "read_timeout_failures": 0, "other_error_failures": 0}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                status = json.load(f)
                # 確保所有鍵都存在，若舊的狀態檔沒有新鍵，則補上
                default_status.update(status)
                return default_status
        except (json.JSONDecodeError, TypeError):
            logging.warning(f"狀態檔 {path} 格式錯誤或為空，將使用初始狀態。")
            return default_status
    return default_status

def save_system_status(status):
    """保存系統狀態檔案"""
    path = config["alerting"]["consecutive_failures_alert"]["status_file_path"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

# =====================
# 主流程
# =====================
def main():
    logging.info("================== 開始執行地震通知腳本 ==================")

    # 先讀取目前的系統狀態
    system_status = load_system_status()

    try:
        # ---------------------
        # 1. 取得地震資料
        # ---------------------
        logging.info(f"正在從 CWA API ({config['earthquake']['api_url']}) 獲取地震資料...")
        requests.packages.urllib3.disable_warnings()

        api_retries = config["earthquake"].get("retries", 1)
        data = None 
        api_request_successful = False # 新增一個旗標來追蹤成功狀態

        for attempt in range(api_retries + 1):
            try:
                r = requests.get(
                    config["earthquake"]["api_url"],
                    headers={"Authorization": config["earthquake"]["api_key"]},
                    timeout=15,
                    verify=False
                )
                r.raise_for_status()
                data = r.json()
                logging.info("成功獲取並解析地震資料 JSON。")

                # 檢查是否需要發送恢復通知
                alert_cfg = config.get("alerting", {}).get("consecutive_failures_alert", {})
                if alert_cfg.get("enabled", False):
                    threshold = alert_cfg.get("threshold", 5)
                    recovered_errors = []
                    for key in ["connect_timeout_failures", "read_timeout_failures", "other_error_failures"]:
                        if system_status.get(key, 0) >= threshold:
                            error_type = key.replace('_failures', '').replace('_', ' ').title()
                            recovered_errors.append(error_type)
                    
                    if recovered_errors:
                        err_str = ", ".join(recovered_errors)
                        logging.info(f"系統已從連續錯誤中恢復 ({err_str})，發送恢復通知。")
                        send_email("【✅ Recovery】地震速報程式連線已恢復", f"CWA API 連線已恢復正常。\n\n先前發生的連續錯誤 ({err_str}) 已解除。")
                        send_line_message(f"【✅ Recovery】地震速報程式連線已恢復！\n先前錯誤 ({err_str}) 已解除。")

                # API 請求成功，重置所有計數器並設定成功旗標
                system_status["connect_timeout_failures"] = 0
                system_status["read_timeout_failures"] = 0
                system_status["other_error_failures"] = 0
                api_request_successful = True
                break # 成功了就跳出迴圈

            except requests.exceptions.RequestException as e:
                logging.warning(f"API 請求發生暫時性問題 (第 {attempt + 1}/{api_retries + 1} 次): {e}")
                if attempt < api_retries:
                    logging.info("等待 5 秒後進行重試...")
                    time.sleep(5) # 在重試前等待
                else:
                    logging.error("API 請求已達最大重試次數，將進入連續失敗判斷機制。")
                    raise e # 達到最大次數，將最終錯誤拋給外層的 except

        if not api_request_successful:
            # 如果迴圈跑完都沒成功，這裡其實不會被執行到，因為上面的 raise 會中斷流程
            # 但這是一個好的防禦性寫法
            return

        json_path = config["storage"]["earthquake_json_path"].replace("YYYY-MM-DD", today)
        save_json(data, json_path)
        logging.info(f"原始地震資料已保存至: {json_path}")
        
        if config.get("run_mode", {}).get("use_test_data", False):
            logging.warning("注意：目前處於測試模式，正在讀取 test_event.json。")
            test_event_path = os.path.join(base_path, "test_event.json")
            with open(test_event_path, encoding="utf-8-sig") as f:
                data = json.load(f)

        # ---------------------
        # 2. 過濾已通知事件
        # ---------------------
        earthquake_events = data.get("records", {}).get("Earthquake", [])
        if not earthquake_events:
            logging.warning("API 回應成功，但 records.Earthquake 陣列為空或不存在。")
            return

        logging.info(f"API 回傳 {len(earthquake_events)} 筆地震事件，開始進行過濾...")
        notified_cache = load_notified_cache()
        new_events = []

        for event in earthquake_events:
            report_no = event.get("ReportNumber") or f"{event.get('EarthquakeInfo', {}).get('OriginTime')}_{event.get('EarthquakeInfo', {}).get('Epicenter', {}).get('EpicenterLatitude')}_{event.get('EarthquakeInfo', {}).get('Epicenter', {}).get('EpicenterLongitude')}_{event.get('EarthquakeInfo', {}).get('EarthquakeMagnitude', {}).get('MagnitudeValue')}"
            
            if "None" in report_no:
                logging.warning(f"發現一筆結構不完整的事件資料，已跳過: {event}")
                continue

            if report_no in notified_cache:
                logging.info(f"➡️ 事件 {report_no} 已通知過，跳過。")
                continue

            # --- 全新、更穩健的震度與地區解析邏輯 ---
            intensity_data = event.get("Intensity", {})
            counties = set()
            max_intensity_str = "0"

            if "Shindo" in intensity_data:
                shindo_list = intensity_data.get("Shindo", [])
                for s in shindo_list:
                    parts = s.split(' ')
                    if len(parts) > 0:
                        counties.add(parts[0])
                    intensity_val = re.search(r'\d+', s)
                    if intensity_val and int(intensity_val.group(0)) > int(re.search(r'\d+', max_intensity_str).group(0)):
                        max_intensity_str = intensity_val.group(0)

            elif "ShakingArea" in intensity_data:
                shaking_areas = intensity_data.get("ShakingArea", [])
                for area in shaking_areas:
                    county_name = area.get("CountyName")
                    if county_name:
                        counties.add(county_name)
                    area_intensity_str = area.get("AreaIntensity", "0")
                    intensity_val = re.search(r'\d+', area_intensity_str)
                    if intensity_val and int(intensity_val.group(0)) > int(re.search(r'\d+', max_intensity_str).group(0)):
                        max_intensity_str = intensity_val.group(0)
            
            max_intensity = int(re.search(r'\d+', max_intensity_str).group(0)) if re.search(r'\d+', max_intensity_str) else 0
            
            # --- 統一的 Log 輸出 ---
            magnitude = event.get("EarthquakeInfo", {}).get("EarthquakeMagnitude", {}).get("MagnitudeValue", 0)
            logging.info(f"--- 正在檢查事件 {report_no} ---")
            logging.info(f"  - 規模={magnitude} (門檻>={config['earthquake']['min_magnitude']})")
            logging.info(f"  - 最大震度={max_intensity} (門檻>={config['earthquake']['min_intensity']})")
            logging.info(f"  - 影響地區: {', '.join(counties) or '無'}")
            
            # --- 條件判斷 ---
            threshold_logic = config["earthquake"]["threshold_logic"]
            passes_magnitude = magnitude >= config["earthquake"]["min_magnitude"]
            passes_intensity = max_intensity >= config["earthquake"]["min_intensity"]

            # 1. 檢查規模與震度門檻
            threshold_passed = False
            if threshold_logic == "OR":
                if passes_magnitude or passes_intensity:
                    threshold_passed = True
            else: # AND
                if passes_magnitude and passes_intensity:
                    threshold_passed = True
            
            if not threshold_passed:
                logging.info(f"  - 判斷結果: ❌ 未達到規模/震度門檻 ({threshold_logic})，跳過。")
                continue

            # 2. 檢查地區
            region_config = config["earthquake"]["regions"]
            is_target_region = "全台灣" in region_config or any(c in region_config for c in counties)
            
            if not is_target_region:
                logging.info("  - 判斷結果: ❌ 地區不在監控範圍內，跳過。")
                continue
            
            # 如果所有條件都通過
            logging.info("  - 判斷結果: ✅ 條件完全符合，準備發送通知。")
            new_events.append((report_no, event))

        # ---------------------
        # 3. 發送通知
        # ---------------------
        if not new_events:
            logging.info("過濾完成，沒有需要通知的新地震事件。")
            return
        
        logging.info(f"發現 {len(new_events)} 筆新事件，開始發送通知...")
        for report_no, event in new_events:
            logging.info(f"正在處理事件 {report_no} 的通知...")
            
            earthquake_info = event.get("EarthquakeInfo", {})
            origin_time_iso = earthquake_info.get("OriginTime")
            dt_object = datetime.datetime.fromisoformat(origin_time_iso)
            time_str = dt_object.strftime("%Y-%m-%d %H:%M:%S")
            epicenter = earthquake_info.get("Epicenter", {}).get("Location")
            magnitude = earthquake_info.get("EarthquakeMagnitude", {}).get("MagnitudeValue")
            
            intensities_list = []
            intensity_data = event.get("Intensity", {})
            if "Shindo" in intensity_data:
                intensities_list = intensity_data.get("Shindo", [])
            elif "ShakingArea" in intensity_data:
                for area in intensity_data.get("ShakingArea", []):
                    if area.get("CountyName") and "地區" in area.get("AreaDesc", ""):
                         intensities_list.append(f"{area.get('CountyName')} {area.get('AreaIntensity', '')}")
            intensities = ", ".join(intensities_list)

            health_check_results = []
            all_systems_ok = True
            if config["health_check"]["enabled"]:
                logging.info("執行伺服器健康檢查...")
                targets = config["health_check"]["allowed_ips"] + config["health_check"]["allowed_domains"]
                for target in targets:
                    result = check_reachability(target, config["health_check"]["timeout_ms"], config["health_check"]["retries"])
                    health_check_results.append(result)
                    if "Fail" in result["status"]:
                        all_systems_ok = False
                logging.info("伺服器健康檢查完成。")
            
            status_tag = "OK" if all_systems_ok else "FAIL"
            subject = f"[伺服器健康檢查: {status_tag}] 地震速報 (M {magnitude}) - {epicenter}"

            # alarm_email內容
            html_content = create_alarm_email(time_str, epicenter, magnitude, intensities, config, health_check_results, all_systems_ok)
            # line message內容
            plain_text_content = f"🚨 地震速報\n🗓️ 時間: {time_str}\n📍 地點: {epicenter}\n📏 規模: {magnitude}\n🏠 震度: {intensities}"
            
            send_email(subject, html_content, attach_json_path=json_path)
            send_line_message(plain_text_content)
            
            notified_cache.add(report_no)
            logging.info(f"事件 {report_no} 的通知已處理完畢，並加入快取。")

        save_notified_cache(notified_cache)
        logging.info(f"已更新通知快取檔案: {config['storage']['cache_notified_path']}")

    except requests.RequestException as e:
         # 當所有重試都失敗後，才會進入這個區塊
         # 所有重試都失敗，這是一個需要記錄的「事件」，但還不一定是「緊急錯誤」
        error_msg = f"HTTP 請求最終失敗: {e}"
        official_msg = ""
        
        # 嘗試解析官方回傳的 HTML 內容 (例如：伺服器維護中)
        if hasattr(e, 'response') and e.response is not None:
            try:
                html_content = e.response.text
                if html_content:
                    # 尋找 <span class="key-content"> 或 <title>
                    match = re.search(r'<span class="key-content">(.*?)</span>', html_content)
                    if not match:
                        match = re.search(r'<title>(.*?)</title>', html_content)
                    
                    if match:
                        official_msg = match.group(1).strip()
                        error_msg += f" (官方訊息: {official_msg})"
            except Exception as parse_e:
                logging.warning(f"嘗試解析官方錯誤回應內容失敗: {parse_e}")

        logging.error(error_msg, exc_info=False)

        alert_cfg = config["alerting"]["consecutive_failures_alert"]
        if not alert_cfg["enabled"]:
            # 如果沒啟用連續告警，則每次失敗都視為需要注意的錯誤
            logging.error("連續失敗告警功能已關閉，將直接發送通知。")
            email_body = f"地震資料抓取失敗(重試後)，請檢查網路連線或 API 金鑰。\n\n錯誤詳情:\n{e}"
            if official_msg:
                email_body += f"\n\n🚨 官方伺服器訊息:\n{official_msg}"
            send_email("【Warning】地震速報程式錯誤通知", email_body)
            
            line_msg = "【Warning】地震速報程式錯誤：地震資料抓取失敗(重試後)！"
            if official_msg:
                line_msg += f"\n官方訊息: {official_msg}"
            send_line_message(line_msg)
        else:
            counter_key = "connect_timeout_failures"
            error_name = "Connection Error"

            if isinstance(e, requests.exceptions.ConnectTimeout):
                counter_key = "connect_timeout_failures"
                error_name = "ConnectTimeout"
            elif isinstance(e, requests.exceptions.ReadTimeout):
                counter_key = "read_timeout_failures"
                error_name = "ReadTimeout"
            # 若為 HTTPError (例如 502/504)，可顯示更明確的狀態
            elif isinstance(e, requests.exceptions.HTTPError):
                counter_key = "other_error_failures"
                error_name = f"HTTP {e.response.status_code} Error"

            system_status[counter_key] = system_status.get(counter_key, 0) + 1

            failures_count = system_status[counter_key]
            threshold = alert_cfg["threshold"]

            # 措辭調整：從「偵測到錯誤」改為更中性的「狀態更新」
            logging.info(f"狀態更新: 偵測到 {error_name} 事件，連續失敗計數: {failures_count}/{threshold}")

            # 只有在剛好達到門檻時，才發送唯一一次的「錯誤」通知
            if failures_count == threshold:
                logging.error(f"【注意】連續 {error_name} 失敗已達 {threshold} 次門檻，觸發首發告警！")
                
                email_body = f"地震資料抓取已連續發生 {threshold} 次 {error_name} 錯誤，請檢查伺服器網路狀態或 CWA API 服務。\n\n最新錯誤詳情:\n{e}"
                if official_msg:
                    email_body += f"\n\n🚨 官方伺服器訊息:\n{official_msg}"
                    
                send_email(f"【Warning】地震速報程式連續 {threshold} 次連線失敗", email_body)
                
                line_msg = f"【Warning】地震速報程式連續 {threshold} 次連線失敗 ({error_name})！"
                if official_msg:
                    line_msg += f"\n官方訊息: {official_msg}"
                send_line_message(line_msg)
            
            elif failures_count > threshold:
                # 超過門檻後保持沉默，避免告警疲勞
                logging.info(f"【注意】連續 {error_name} 失敗持續中 (第 {failures_count} 次)，為避免告警疲勞，本次不發送重複通知。")

    finally:
        # ---------------------
        # 4. 清理舊檔案
        # ---------------------

        # 無論成功或失敗，都在最後儲存更新後的狀態
        save_system_status(system_status)

        # 確保不論程式如何結束，清理工作都會被執行
        logging.info("開始檢查並清理舊的資料與日誌檔案...")
        
        earthquake_folder = os.path.dirname(config["storage"]["earthquake_json_path"])
        json_retention_days = config["storage"].get("json_retention_days", 10)
        deleted_json_files = clean_old_files(earthquake_folder, "earthquake_json_", json_retention_days)
        if deleted_json_files:
            logging.info(f"共清理了 {len(deleted_json_files)} 個過期的 JSON 檔案。")
            for file_path in deleted_json_files:
                logging.info(f"  - 已刪除: {file_path}")
        else:
            logging.info("檢查完畢，沒有過期的 JSON 檔案需要清理。")

        log_folder = "logs"
        log_retention_days = config["storage"].get("log_retention_days", 14)
        error_log_retention_days = config["storage"].get("error_log_retention_days", 30)
        
        deleted_log_files = clean_old_files(log_folder, "logs_", log_retention_days)
        if deleted_log_files:
            logging.info(f"共清理了 {len(deleted_log_files)} 個過期的一般日誌。")
            for file_path in deleted_log_files:
                logging.info(f"  - 已刪除: {file_path}")
        else:
            logging.info("檢查完畢，沒有過期的一般日誌需要清理。")
            
        deleted_error_files = clean_old_files(log_folder, "error_", error_log_retention_days)
        if deleted_error_files:
            logging.info(f"共清理了 {len(deleted_error_files)} 個過期的錯誤日誌。")
            for file_path in deleted_error_files:
                logging.info(f"  - 已刪除: {file_path}")
        else:
            logging.info("檢查完畢，沒有過期的錯誤日誌需要清理。")

        logging.info("舊檔案清理完畢。")

        logging.info("================== 本次地震通知腳本執行完畢 ==================\n")

if __name__ == "__main__":
    main()