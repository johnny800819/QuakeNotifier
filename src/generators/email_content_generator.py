# generators/email_content_generator.py

def create_alarm_email(time_str, epicenter, magnitude, intensities, config, health_check_results, all_systems_ok):
    # --- 1. 產生「監測區域影響報告」區塊 ---
    
    # 先將 "臺北市 4級, 新北市 3級" 這樣的字串，解析成 {'臺北市': '4級', '新北市': '3級'} 的字典，方便查詢
    all_intensities_dict = {}
    for item in intensities.split(','):
        parts = item.strip().split(' ')
        if len(parts) == 2:
            all_intensities_dict[parts[0]] = parts[1]

    # 產生監測區域的表格內容 (HTML rows)
    monitored_area_rows = ""
    monitored_regions_config = config['earthquake']['regions']

    # 判斷是監控全台灣還是特定區域
    regions_to_display = []
    if "全台灣" in monitored_regions_config:
        # 如果是全台灣，就顯示所有受影響的地區
        regions_to_display = sorted(all_intensities_dict.keys()) # 排序讓顯示更整齊
    else:
        # 如果是特定區域，就只顯示設定檔中的區域
        regions_to_display = monitored_regions_config

    has_monitored_data = False
    for region in regions_to_display:
        # 從解析好的字典中，取得該地區的觀測震度
        observed_intensity = all_intensities_dict.get(region)
        if observed_intensity: # 只顯示有觀測到震度的地区
            has_monitored_data = True
            monitored_area_rows += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">{region}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; font-size: 1.2em; color: #d9534f;"><strong>{magnitude}</strong></td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; font-size: 1.2em; color: #d9534f;"><strong>{observed_intensity}</strong></td>
            </tr>
            """
            
    # 如果遍歷完所有監控區域都沒有震度資料，顯示提示訊息
    if not has_monitored_data:
        monitored_area_rows = '<tr><td colspan="3" style="padding: 15px; text-align: center; color: #777;">您監控的區域在此次地震中未觀測到震度。</td></tr>'


    # 組合完整的「監測區域影響報告」HTML
    monitored_area_html = f"""
    <h2 style="color: #d9534f; border-bottom: 2px solid #d9534f; padding-bottom: 10px;">🎯 監測區域影響報告</h2>
    
    <table style="width: 100%; border-collapse: collapse; margin-top: 15px; text-align: center;">
        <tr style="background-color:#f2f2f2;">
            <th style="padding: 10px;">監測地區</th>
            <th style="padding: 10px;">地震規模</th>
            <th style="padding: 10px;">觀測震度</th>
        </tr>
        {monitored_area_rows}
    </table>
    <div style="background-color: #f5f5f5; padding: 10px; border-radius: 5px; margin-top: 20px;">
        <h4 style="margin-top:0; margin-bottom: 10px; color: #333;">觸發條件</h4>
        <ul style="list-style: none; padding-left: 0; margin: 0; font-size: 0.9em;">
            <li><strong>監控區域:</strong> {', '.join(config['earthquake']['regions'])}</li>
            <li><strong>規模門檻:</strong> &gt;= {config['earthquake']['min_magnitude']}</li>
            <li><strong>震度門檻:</strong> &gt;= {config['earthquake']['min_intensity']}</li>
            <li><strong>判斷邏輯:</strong> {config['earthquake']['threshold_logic']}</li>
        </ul>
    </div>
    """

    # --- 2. 產生「伺服器健康檢查」區塊 (邏輯不變) ---
    health_check_html = ""
    if config["health_check"]["enabled"]:
        summary_status = ('<h4 style="color: #5cb85c;">✅ 全數正常</h4>' if all_systems_ok else '<h4 style="color: #d9534f;">❌ 部分異常</h4>')
        details_rows = ""
        for res in health_check_results:
            status_color = "#5cb85c" if "OK" in res["status"] else "#d9534f"
            details_rows += f'<tr><td style="padding: 8px; border-bottom: 1px solid #ddd;">{res["target"]}</td><td style="padding: 8px; border-bottom: 1px solid #ddd;">{res["method"]}</td><td style="padding: 8px; border-bottom: 1px solid #ddd; color: {status_color};">{res["status"]}</td><td style="padding: 8px; border-bottom: 1px solid #ddd;">{res["latency"]}</td></tr>'
        health_check_html = f'''
        <h2 style="color: #337ab7; border-bottom: 2px solid #337ab7; padding-bottom: 10px; margin-top: 30px;">🩺 伺服器健康檢查</h2>
        {summary_status}
        <table style="width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.9em;">
            <tr style="background-color:#f2f2f2;"><th style="padding: 8px; text-align: left;">目標</th><th style="padding: 8px; text-align: left;">方式</th><th style="padding: 8px; text-align: left;">狀態</th><th style="padding: 8px; text-align: left;">延遲</th></tr>
            {details_rows}
        </table>'''

    # --- 3. 產生「震源詳細資料」區塊 ---
    source_details_html = f"""
    <h2 style="color: #777; border-bottom: 2px solid #777; padding-bottom: 10px; margin-top: 30px;">震源詳細資料</h2>
    <table style="width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 0.9em;">
        <tr><td style="padding: 10px; background-color: #f9f9f9; width: 120px;"><strong>🗓️ 時間</strong></td><td style="padding: 10px;">{time_str}</td></tr>
        <tr><td style="padding: 10px; background-color: #f9f9f9;"><strong>📍 震央</strong></td><td style="padding: 10px;">{epicenter}</td></tr>
        <tr><td style="padding: 10px; background-color: #f9f9f9;"><strong>📏 規模</strong></td><td style="padding: 10px;">{magnitude}</td></tr>
        <tr><td style="padding: 10px; background-color: #f9f9f9;"><strong>🏠 各地總震度</strong></td><td style="padding: 10px;">{intensities}</td></tr>
    </table>
    """

    # --- 4. 組合最終 Email 內容 (依照新的順序) ---
    final_html_content = f"""
    <html><body>
    <div style="font-family: Arial, sans-serif; max-width: 600px; border: 1px solid #ddd; border-radius: 10px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
      {monitored_area_html}
      {health_check_html}
      {source_details_html}
    </div>
    </body></html>
    """
    return final_html_content