# Superset panoları (P7.5)

Bu klasör, Superset 6.1.0'ın kendi dışa aktarıcısıyla (`superset export-dashboards`) alınmış v1 demetidir:
`metadata.yaml`, `databases/`, `datasets/`, `charts/`, `dashboards/`. Panolar yalnızca `warehouse_db.marts` şemasını okur.

| Pano | Kaynak mart |
|---|---|
| Envanter özeti / Inventory summary | `mart_inventory_summary` (QBank ve korpus) |
| Risk dağılımı / Risk distribution | `mart_risk_features` (gümüş etiket; Model A sınıfı yalnız yayımlanmış altın Model A varken dolar) |
| Korpus istatistikleri / Corpus statistics | `mart_inventory_summary` (CORPUS), `mart_service_runtime`, `mart_topology_coverage` |
| Kripto arketipleri / Crypto archetypes | `mart_archetypes` |
| Model metrikleri / Model metrics | `mart_model_metrics` |
| Bekçi kalitesi / Guardrail quality | `mart_guardrail_quality` |

## Yükleme

```
make up PROFILES="data"
make superset-import
```

`make superset-import`, `superset` konteynerinde `/app/pythonpath/quancrypt_import.py`'yi çalıştırır. Betik bu klasörü
(`/bundle`, salt okunur) Superset'in `ImportDashboardsCommand`'ıyla yükler. Bağlantı `warehouse_reader` rolüyledir. Demetteki
adres maskeli parola taşır (`XXXXXXXXXX`); gerçek parola içe aktarmada `WAREHOUSE_READER_PASSWORD` ortam değişkeninden verilir ve
Superset'in meta veritabanında `SUPERSET_SECRET_KEY` ile şifreli saklanır.

Superset 6.1.0'ın içe aktarıcısı panoları her seferinde yeniden yazar, ama aynı kimlikli (uuid) veri kümelerini ve grafikleri
olduğu gibi bırakır. Bir grafiği değiştirdikten sonra temiz yükleme için `superset-home` volume'ü silinir ve yeniden kurulur.

## Değiştirme

Panoyu arayüzde düzenleyin, `superset export-dashboards -f <dosya>.zip` ile dışa aktarın ve zip'in kök klasörünün içeriğini
buraya koyun. Dışa aktarımda parola maskelidir; kullanıcı adı, e-posta veya proje anahtarı bulunmaz (yine de commit'ten önce
`grep -ri "password\|@" .` ile bakın).
