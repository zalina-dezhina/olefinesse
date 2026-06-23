# 00b_clean/

**EN:** Clean data extraction. Connects to Databricks, detects cracking cycles (via feed drop), applies all cuts (decoke / warmup / tail), saves `{FURNACE}_clean.parquet`. This is the ONLY notebook that touches Databricks.

**RU:** Чистая выгрузка данных. Подключается к Databricks, определяет циклы крекинга (по падению подачи), применяет все разрезы (декокс / прогрев / хвост), сохраняет `{FURNACE}_clean.parquet`. Это ЕДИНСТВЕННЫЙ ноутбук который обращается к Databricks.

**Output / Выход:** `output/{FURNACE}/00b_clean/{FURNACE}_clean.parquet`
