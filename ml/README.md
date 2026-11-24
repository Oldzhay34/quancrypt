# ml

Quancrypt'in makine öğrenmesi paketi (P7). Hexagonal düzendedir (hexagonal-service, ml-pipeline §1). P7.1 yalnız
etiketleme ve kapsam veri setini içerir; model eğitimi P7.2 ve P7.3'tedir.

Komut satırı host'ta çalışır ve kök `.env` dosyasındaki değişkenleri `make ml` ile alır (Claude Code `.env`'i okumaz).

## Komutlar

```
make ml ARGS="migrate"                       # warehouse_db.labels şemasını kurar (warehouse_db_migrator)
make ml ARGS="label-export"                  # 300 bulguluk tabakalı örneklem -> labeling/batch_001.csv (60'ı çift)
make ml ARGS="label-import labeling/batch_001.csv --labeler FIRST"
make ml ARGS="label-import labeling/batch_001_second.csv --labeler SECOND"
make ml ARGS="label-resolve"                 # labeling/batch_001_disagreements.csv'deki çözümleri yazar
make scope-dataset                           # kapsam veri setini üretir ve 70/15/15 böler
make verify                                  # ruff, mypy --strict, import-linter, pytest (gerçek PostgreSQL), kapsam
```

`label-export` analizcinin çalışmasını (compose `app` profili, `CORPUS_ROOT` bağlı) ve ön işleme ile warehouse build'inin
yapılmış olmasını ister. Her içe aktarma `reports/labeling.md` raporunu (Cohen kappa, uyuşmazlıklar) yeniden yazar.

## Veri

- Kaynak `marts.mart_risk_features`'tır (yalnız CORPUS ve BENCHMARK satırları, D-317h).
- Etiketleme dışa aktarımı korpus bulgularının gerçek dosya ve satırını `raw.event`'ten okur; bu, ml-pipeline §2'deki "raw okunmaz" kuralının kayıtlı tek istisnasıdır (D-322b). Konum yalnız git dışı CSV'ye yazılır.
- Etiketler `warehouse_db.labels` şemasındadır (`migrations/`, sürüm tablosu `ml_alembic_version`). Bir projenin onayı geri alınırsa data-platform `labels.labeled_finding` satırlarını, parti kalemleri, etiketleri ve çözümleriyle birlikte siler.
- Kapsam veri seti `data/scope/` altındadır; test kümesi `services/agent-service/data/examples/scope_set.jsonl`'e kopyalanır (tek kaynak `ml/`).
