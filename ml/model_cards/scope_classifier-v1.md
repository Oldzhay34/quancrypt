# Model kartı: scope_classifier-v1

## Amaç
Kapsam bekçisinin 2. halkası: kullanıcının isteğini kapsam içi (projenin kriptosu ve kuantum-güvenli geçiş) veya kapsam dışı diye ayırmak. Güvenli bölgelerde karar verir, aradaki istekleri 3. halkaya bırakır (guardrails-security §2; agent-service bağlantısı P7.5).

## Veri
- Onaylı kapsam seti (D-326): 840 kayıt, TR ve EN, parafraz grubuna göre bölünmüş (D-323i).
- Etiket kaynağı `SCOPE_SET`.

## Model
- Gömme modeli: `embeddinggemma:latest`, Ollama özeti `85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1`, 768 boyut. Çıkarımda aynı model ve aynı istekle gömülmelidir; özet değişirse model yeniden eğitilir.
- Sınıflandırıcı başı: LINEAR_SVM (StandardScaler + sınıflandırıcı); ONNX yalnız bu başı içerir.
- Eşik 0.0316; UNSURE bandı [0.0259, 0.4332); `scope_classifier-v1.thresholds.json`.

## Metrikler (test)
- Kapsam dışı recall %100.0, yanlış ret %42.1; TR recall %100.0, EN recall %100.0.
- UNSURE oranı %24.8.
- H4: tutmadı.

## Sınırlamalar
- Sentetik set; küçük doğrulama ve test kümeleri; jailbreak örneklemi küçük.
- Yeni biçimdeki enjeksiyonlara karşı tek başına yeterli değildir; 1. ve 3. halkalarla birlikte çalışır.

## Adalet ve kapsam notları
- Yalnız TR ve EN eğitildi; başka dillerde davranışı ölçülmedi. Kapsam kararı kaydı istek metnini tutmaz (guardrails-security §2); sohbet mesajları ayrıca sohbet geçmişinde saklanır (D-225).

## Kullanım dışı durumlar
- Başka bir gömme modeli veya özetiyle çalıştırmak; 2. halkayı tek başına bekçi olarak kullanmak.
