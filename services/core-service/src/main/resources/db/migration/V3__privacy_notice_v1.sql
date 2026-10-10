-- Privacy notice version 1 (D-135, D-159). Drafted by Claude Code; the text is approved by the product owner at the P2.3 gate.

INSERT INTO privacy_notice (id, version, text_tr, text_en, published_at) VALUES (
    '6f1d2c0e-3b7a-4c55-9e21-5a0b7d4e8c01',
    1,
    'Quancrypt aydınlatma metni (sürüm 1)

Quancrypt bu makinede yerel olarak çalışır. Aşama 1''de hiçbir veri makineden çıkmaz; bulut hizmeti, ücretli API veya dış dil modeli kullanılmaz.

Analiz için onay gerekmez. Tarama, bulgular, topoloji ve geçiş planı yalnızca yerel core-service veritabanında tutulur. Proje kimliği (kök yol veya git adresi) saklanmaz; yerine bu kurulumun gizli anahtarıyla hesaplanan tek yönlü bir özet (HMAC-SHA256) tutulur.

İki ayrı ve isteğe bağlı onay vardır; ikisi de varsayılan olarak kapalıdır:
1. WAREHOUSE_ANALYTICS: Projenizden üretilen anonim olaylar (algoritma ailesi, kullanım bağlamı, öncelik, sayılar ve sürüm numaraları gibi kodlu alanlar; dosya yolu, kaynak kod veya serbest metin yok) yerel analiz deposuna (warehouse) gönderilir ve panolarda kullanılır.
2. MODEL_TRAINING: Aynı anonim veriler yerel risk modellerinin eğitiminde kullanılır.

Onayı istediğiniz zaman geri alabilirsiniz. WAREHOUSE_ANALYTICS onayını geri aldığınızda henüz gönderilmemiş olaylar silinir ve warehouse''taki türev verilerin silinmesi istenir. Projeyi sildiğinizde projeye ait tüm kayıtlar silinir; yalnızca anonim proje özeti ve eylem kodundan oluşan denetim kaydı ile daha önce gönderilmiş anonim olaylar kalır.',
    'Quancrypt privacy notice (version 1)

Quancrypt runs locally on this machine. In stage 1 no data leaves the machine; no cloud service, paid API or external language model is used.

Analysis does not require consent. Scans, findings, the topology and the migration plan are kept only in the local core-service database. The project identity (root path or git address) is not stored; a one-way digest (HMAC-SHA256) computed with this installation''s secret key is kept instead.

There are two separate, optional consents; both are off by default:
1. WAREHOUSE_ANALYTICS: Anonymous events derived from your project (coded fields such as algorithm family, usage context, priority, counts and version numbers; no file paths, source code or free text) are sent to the local analytics store (warehouse) and used in dashboards.
2. MODEL_TRAINING: The same anonymous data is used to train local risk models.

You can withdraw a consent at any time. When you withdraw WAREHOUSE_ANALYTICS, events not yet sent are deleted and the deletion of derived data in the warehouse is requested. When you delete a project, all of its records are deleted; only the audit entry, made of the anonymous project digest and an action code, and anonymous events already sent remain.',
    TIMESTAMPTZ '2026-10-09 00:00:00+00'
);
