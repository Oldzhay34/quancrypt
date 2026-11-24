# Etiket partileri

Bu klasör `ml label-export` çıktılarını tutar. CSV dosyaları git dışıdır (`ml/.gitignore`), çünkü korpus depolarının
gerçek dosya yollarını ve redakte kod bağlamını içerir (D-322a).

- `batch_001.csv`: 1. etiketleyicinin dolduracağı parti (300 bulgu). `double_label = true` olan 60 satır daha sonra yeniden etiketlenir.
- `batch_001_second.csv`: tekrar etiketlemenin kopyası (D-325: aynı kişi, 300'ü bitirdikten birkaç gün sonra, ilk etiketlere bakmadan; yalnız `double_label = true` satırlar doldurulur).
- `batch_001_disagreements.csv`: iki etiketleyici de içe aktarılınca yazılır; uyuşmazlıkların çözümü bu dosyaya yazılır.

Doldurulacak kolonlar `label` (CRITICAL, HIGH, MEDIUM, LOW), `labeler` (takma ad veya baş harfler) ve isteğe bağlı `notes`'tur.
Kurallar `docs/data/labeling_guideline.md`'dedir.
