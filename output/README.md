# output/

**EN:** All analysis outputs. Organised by furnace then by stage. Never commit large parquet/png files to git — add them to .gitignore.

**RU:** Все результаты анализа. Организовано по печи затем по стадии. Никогда не коммитить большие parquet/png файлы в git — добавить в .gitignore.

## Structure / Структура

```
output/
  {FURNACE}/          ← one per furnace (1HA…1HG)
    00b_clean/        ← clean parquet + run windows
    01_tags/          ← tag anomaly inventory + plots
    02a_corr_furnace/ ← furnace-wide correlations
    02b_corr_passes/  ← per-pass correlations
    03_trajectories/  ← ΔΔ vs run_age plots
  fleet/
    00_summary/       ← cross-furnace comparison
    05_forecaster/    ← trained model + predictions
```

## Rule / Правило

A file lives in `output/1HA/` only if it was computed from 1HA data alone.
A file lives in `output/fleet/` only if it required combining ≥2 furnaces.
Файл живёт в `output/1HA/` только если посчитан из данных 1HA.
Файл живёт в `output/fleet/` только если потребовал объединения ≥2 печей.
