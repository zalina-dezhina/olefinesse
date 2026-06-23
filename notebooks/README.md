# notebooks/

**EN:** One notebook per analysis stage. All per-furnace notebooks are parametrized with `FURNACE` variable and run in parallel via `bash run_all_furnaces.sh`. Fleet notebooks run once after all furnaces are complete.

**RU:** Один ноутбук на стадию анализа. Все ноутбуки на печь параметризованы переменной `FURNACE` и запускаются параллельно через `bash run_all_furnaces.sh`. Флотские ноутбуки запускаются один раз после всех печей.

## Stage order / Порядок стадий

| # | Notebook | Scope | Status |
|---|---|---|---|
| 00b | `00b_clean/` | per furnace | ✅ Ready |
| 01 | `01_tags/` | per furnace | 🔜 Build next |
| 02a | `02a_corr_furnace/` | per furnace | 🔜 Build next |
| 02b | `02b_corr_passes/` | per furnace | 📋 Planned |
| 03 | `03_trajectories/` | per furnace | 📋 Planned |
| 00 | `00_summary/` | fleet | 📋 Planned |
| 05 | `05_forecaster/` | fleet | 🔮 Future |

## Rule / Правило

**EN:** Always read from `output/{FURNACE}/00b_clean/{FURNACE}_clean.parquet`. Never query Databricks in notebooks 01+. Clean once, analyse many times.

**RU:** Всегда читать из `output/{FURNACE}/00b_clean/{FURNACE}_clean.parquet`. Никогда не запрашивать Databricks в ноутбуках 01+. Очистить один раз, анализировать много раз.
