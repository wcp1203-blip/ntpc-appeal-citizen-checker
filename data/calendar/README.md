# 政府行政機關辦公日曆表（國定假日 / 補班日資料）

供 `core/holidays.py` 判斷「非上班日」，讓訴願期間末日順延計算能認得國定假日、
彈性放假與補班日，而不是只跳過週六日。

## 資料來源

- **原始權威來源**：行政院人事行政總處「中華民國政府行政機關辦公日曆表」，
  發布於政府資料開放平臺 data.gov.tw（dataset 14718）。
  <https://data.gov.tw/dataset/14718>
- **實際下載管道**：社群維護的 JSON 鏡像 `ruyut/TaiwanCalendar`（內容即為上述政府
  原始資料轉成每日 JSON），透過 jsDelivr CDN 取得。
  <https://github.com/ruyut/TaiwanCalendar>

## 下載日期

2026-10-24（民國115年10月24日）。

重新下載方式：

```bash
python data/calendar/_fetch_calendar.py
```

## 涵蓋年份

2024、2025、2026、2027（民國113–116年）。

> ⚠️ 若使用者輸入的日期落在未涵蓋的年份，`core/holidays.py` 會退回「只判斷週末」，
> 並回傳 `calendar_complete=False` 旗標，介面須提醒使用者自行確認國定假日。

## 檔案格式

每個 `<year>.json`：

```json
{
  "year": 2026,
  "source": "<下載來源 URL>",
  "days": {
    "2026-02-18": {"holiday": true,  "desc": "春節"},
    "2025-02-08": {"holiday": false, "desc": "補行上班"}
  }
}
```

`days` 只收錄「與預設週末規則不同」或「有名稱的國定假日」之日子，以保持精簡、
便於人工核對：

- `holiday: true` 且落在平日 → 國定假日 / 彈性放假 / 補假（**視為放假日**）
- `holiday: false` 且落在週末 → 補班日（**視為上班日，期限不在此順延**）
- 落在週末、有名稱的國定假日也會收錄，方便核對，但本來就放假，不影響計算

未出現在 `days` 的日子，依預設規則：週六日為放假、週一至週五為上班。
