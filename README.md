# QuakeNotifier - 地震速報通知系統

這是一個 Python 地震速報通知系統，透過介接中央氣象署 (CWA) Open Data API，即時監控地震資訊，並在符合特定條件（如規模、震度、地區）時，透過 Email 與 LINE Notify 發送警報。

## ✨ 功能特色

*   **即時監控**：定期抓取 CWA 地震資料。
*   **彈性過濾**：
    *   可設定最小規模 (Magnitude) 與最小震度 (Intensity) 門檻。
    *   支援「且 (AND)」或「或 (OR)」的門檻判斷邏輯。
    *   可指定監控特定縣市（如「新北市」）或「全台灣」。
*   **多管道通知**：
    *   **Email**：發送包含詳細地震資訊、震度分佈表格的 HTML 郵件。
    *   **LINE Notify**：發送簡潔的即時文字快訊。
*   **伺服器健康檢查**：在發送地震通知的同時，順便檢查關鍵伺服器（IP 或 Domain）的連線狀態，並附在 Email 報告中。
*   **自動化維護**：自動清理過期的日誌與暫存資料。
*   **連續失敗告警**：當 API 連線連續失敗超過設定次數時，自動發送告警通知。

## 📂 專案結構

```text
QuakeNotifier/
├── src/                    # 原始碼目錄
│   ├── certs/              # SSL 憑證相關 (若有)
│   ├── generators/         # 通知內容產生器 (Email HTML 等)
│   ├── quakeNotifier.py    # 主程式
│   ├── config.json.template# 設定檔範本
│   └── test_event.json     # (選用) 測試用的地震資料
├── scripts/                # 執行腳本
│   └── run_notifier_for_exe.bat # 執行封裝後 EXE 的批次檔
├── docs/                   # 文件
├── logs/                   # 執行日誌
├── earthquakeData/         # 原始地震 JSON 存檔
├── cacheNotified/          # 已通知事件的快取紀錄
├── dist/                   # 建置後的執行檔輸出目錄
└── QuakeNotifier.spec      # PyInstaller 封裝設定檔
```

## 🚀 安裝與設定

### 1. 環境準備

確保已安裝 Python。

```bash
# 安裝相依套件
pip install -r docs/requirements.txt
```

### 2. 設定檔

請將 `src/config.json.template` 複製為 `src/config.json`，並填入您的資訊：

```json
{
  "earthquake": {
    "api_key": "您的_CWA_API_KEY",  // 請至氣象署開放資料平台申請
    "regions": ["全台灣"]           // 或指定 ["臺北市", "新北市"]
  },
  "notification": {
    "line_message": {
      "line_message_token": "您的_LINE_NOTIFY_TOKEN"
    },
    "email": {
      "smtp_server": "smtp.example.com",
      "recipients": ["user@example.com"]
    }
  }
}
```

## 🛠️ 使用方法

### 直接執行 Python 原始碼

```bash
python src/quakeNotifier.py
```

### 封裝為執行檔 (EXE)

```bash
pyinstaller QuakeNotifier.spec
```

封裝完成後，執行檔位於 `dist/QuakeNotifier.exe`。
您可以使用 `scripts/run_notifier_for_exe.bat` 來執行它（請確保 `config.json` 與 exe 位於同一目錄，或依據腳本路徑配置）。

## 🧪 測試模式 (Testing Mode)

若您希望在沒有真實地震發生時測試通知功能，可以啟用測試模式。

1.  在 `config.json` 中設定：
    ```json
    "run_mode": {
      "use_test_data": true
    }
    ```
2.  在 `src/` 目錄下建立 `test_event.json` 檔案。
    *   *注意：此檔案已被 `.gitignore` 忽略，請自行建立。*

**`test_event.json` 範例內容：**

```json
{
  "success": "true",
  "result": {
    "resource_id": "E-A0015-001",
    "fields": []
  },
  "records": {
    "Earthquake": [
      {
        "EarthquakeNo": "113000",
        "ReportNumber": "113000",
        "ReportColor": "綠色",
        "ReportContent": "01/01 00:00 地點...",
        "EarthquakeInfo": {
          "OriginTime": "2025-01-01 12:00:00",
          "FocalDepth": 10.0,
          "EarthquakeMagnitude": {
            "MagnitudeType": "芮氏規模",
            "MagnitudeValue": 6.5
          },
          "Epicenter": {
            "Location": "花蓮縣政府南南東方 10.0 公里",
            "EpicenterLatitude": 23.0,
            "EpicenterLongitude": 121.0
          }
        },
        "Intensity": {
          "ShakingArea": [
            {
              "CountyName": "花蓮縣",
              "AreaIntensity": "5弱"
            },
            {
              "CountyName": "臺北市",
              "AreaIntensity": "3級"
            }
          ]
        }
      }
    ]
  }
}
```

## 🚢 Server 部署架構 (Deployment)

本專案在正式環境 (Server) 上的部署結構與開發環境略有不同，採用**最小變動原則**以維持現有排程運作。

### Server 目錄結構

```text
C:\inetpub\wwwroot\QuakeNotifier\
├── dist/                    # 存放最新的 QuakeNotifier.exe 與 config.json
├── logs/                    # 執行日誌
├── earthquakeData/          # 地震資料存檔
├── cacheNotified/           # 已通知紀錄
└── run_notifier_for_exe.bat # 排程器直接呼叫此腳本
```

### 更新部署步驟

1.  **本機封裝**：
    執行 `pyinstaller QuakeNotifier.spec` 產生新的 `dist/QuakeNotifier.exe`。
2.  **檔案複製**：
    將本機 `dist/` 資料夾內的內容，覆蓋至 Server 的 `dist/` 目錄。
3.  **伺服器執行**：
    Server Windows Task Scheduler 執行 `run_notifier_for_exe.bat` **若路徑有異動請記得修改**
    
## ⚠️ 注意事項

*   **資安提醒**：`config.json` 包含 API Key 與密碼，**絕對不要**將其上傳至 GitHub。專案已設定 `.gitignore` 排除此檔案。
*   **快取機制**：程式會將已通知過的地震 ID 記錄在 `cacheNotified/notified_events.json`，避免重複發送。若要重新測試同一筆資料，請手動清理該檔案或修改測試資料的 `ReportNumber`。
