-- Privacy notice version 2 (D-284). Version 1 (V3) stays: an applied migration is never changed, and consents keep the version they
-- were given under. GrantConsent accepts only the latest version (D-135), so the UI shows this one. The text is plain text (the UI
-- renders it as text, never as HTML); it was drafted from the project document's "KVKK, Gizlilik ve Güvenlik Tasarımı" section
-- and is submitted to the product owner for approval at the P5.2 gate (D-290a); docs/kvkk/aydinlatma-metni-tr.md and -en.md hold the same text. Until it is approved the text may still change, because this migration has not been applied anywhere that matters (D-159 precedent).

INSERT INTO privacy_notice (id, version, text_tr, text_en, published_at) VALUES (
    '880ee72e-550d-4fec-a4fe-d5c41bdfd28e',
    2,
    'Quancrypt aydınlatma metni (sürüm 2)

Bu metin hukuki görüş değildir. Ürünleşme aşamasında bir uzmanla gözden geçirilir (VERBİS kaydı dahil).

1. Genel bilgi
Quancrypt, bir Spring Boot projesindeki RSA tabanlı kriptografiyi bulur ve geçiş planı üretir. Okul prototipi olan Aşama 1''de hiçbir veri makinenizden çıkmaz: Quancrypt tamamen bu makinede çalışır; bulut hizmeti, ücretli API, telemetri veya dış dil modeli kullanılmaz. Yapay zekâ yanıtları bu makinedeki yerel bir dil modeli (Ollama) ile üretilir.

2. Hangi veri, hangi amaçla, nerede işlenir?
- Kaynak kod ve yapılandırma (içinde test verisi veya e-posta olabilir): kriptografi kullanımını bulmak için işlenir. Yalnızca yerelde işlenir; analiz servisi projenizi salt okunur görür. Sizin diskinizde kalır, Quancrypt kopyalamaz.
- Kaynak koddaki sırlar (parola, özel anahtar, token): saklanmaz; yerelde tespit edilip maskelenir. Ancak sohbete kendiniz yazdığınız metin, içinde sır olsa bile, olduğu gibi yerel sohbet geçmişinde saklanır; sohbete sır yazmayın.
- Yerel dil modeline giden kod parçaları: belirsiz bulguları sınıflandırmak ve soruları yanıtlamak için kullanılır. Yalnızca bu makinedeki yerel modele gider ve ayrıca saklanmaz. Ancak asistanın yanıtı bir kod parçasını alıntılayabilir ve yanıtlar sohbet geçmişinde saklanır.
- Bulgular, topoloji ve geçiş planı: envanter ve riske göre sıralı plan sunmak için yerel core-service veritabanında tutulur; siz projeyi silene kadar saklanır.
- Proje kimliği (kök yol veya git adresi): aynı projeyi tanımak için kullanılır. Yol veya adres saklanmaz; bu kuruluma özel gizli anahtarla hesaplanan tek yönlü bir özet (HMAC-SHA256) saklanır. Projeyi silene kadar tutulur; silinen projenin özeti denetim kayıtlarında, gönderilmeyi bekleyen veya gönderilmiş anonim olaylarda (onay geri alma bildirimi dahil) ve agent veritabanındaki proje başvurusunda kalabilir (bkz. madde 4). Ayrıca projenin görünen adı olarak klasör adı core veritabanında saklanır.
- Sohbet metinleri: sorularınız ve asistanın yanıtları, konuşma geçmişini göstermek için yerel agent veritabanında tutulur. Kapsam dışı bulunan sorular da bu geçmişte durur. Yerel geçmiştir; siz silebilirsiniz (bu sürümde sohbet silme yalnızca servis arayüzü, yani API ile yapılır).
- Kapsam kararı: sorunun Quancrypt konusu içinde olup olmadığını denetlemek için yerelde işlenir. Karar kaydında karar, güven puanı, kararı veren halka, işlem süresi ve dil gibi kodlanmış alanlar tutulur; soru metni bu kayıtta yoktur (soru sohbet geçmişindedir).

3. Onay gerektirmeyen ve gerektiren işleme
Analiz için onay gerekmez. Tarama, bulgular, topoloji ve plan yalnızca yerel veritabanında tutulur.

İki ayrı ve isteğe bağlı onay vardır; ikisi de varsayılan olarak kapalıdır:
1. WAREHOUSE_ANALYTICS (analitik): Projenizden üretilen anonim olaylar (algoritma ailesi, kullanım bağlamı, öncelik, sayılar ve sürüm numaraları gibi kodlu alanlar; dosya yolu, kaynak kod veya serbest metin yok) yerel analiz deposuna (warehouse) gönderilir ve panolarda kullanılır.
2. MODEL_TRAINING (model eğitimi): Aynı anonim veriler yerel risk modellerinin eğitiminde kullanılır.

Onay vermeden devam edebilirsiniz; analiz yine çalışır.

4. Onayı geri alma ve silme
- Onayı istediğiniz zaman Ayarlar ekranından geri alabilirsiniz.
- WAREHOUSE_ANALYTICS onayını geri aldığınızda core veritabanındaki henüz gönderilmemiş olaylar silinir; agent''ın bekleyen kapsam kararı olayları ise gönderilmeden önce onay yeniden denetlenip atılır. Warehouse''taki bu projeye ait kayıtların silinmesi istenir.
- Bir projeyi sildiğinizde projeye ait core veritabanı kayıtları silinir. Anonim proje özeti ile eylem kodundan oluşan denetim kayıtları, gönderilmeyi bekleyen veya gönderilmiş anonim olaylar (onay geri alma bildirimi dahil) ve agent veritabanındaki proje başvurusu kalabilir. Sohbet geçmişi ayrı bir yerel veritabanındadır ve proje silinirken kendiliğinden silinmez; sohbet oturumlarını ayrıca silmeniz gerekir.
- Sohbet geçmişini siz silebilirsiniz (bu sürümde yalnızca API ile).

5. İleride merkezi kullanım (bilgi)
Bu prototipte veri merkeze gönderilmez. İleride merkezi bir hizmet eklenirse yalnızca onayınızla ve yalnızca anonim, kodlanmış bulgu verileri (kod yerine metadata) gönderilir; bu durumda bu metin yeniden yayımlanır ve onayınız yeniden istenir.

6. Güvenlik
Arayüz yalnızca bu makinenin yerel adresinden (127.0.0.1) erişilebilir ve her kurulumda rastgele üretilen bir oturum anahtarı ister.',
    'Quancrypt privacy notice (version 2)

This text is not legal advice. It is reviewed by a specialist when the product is commercialised (including the VERBİS registration).

1. General information
Quancrypt finds RSA-based cryptography in a Spring Boot project and produces a migration plan. In stage 1, the school prototype, no data leaves your machine: Quancrypt runs entirely on this machine; no cloud service, paid API, telemetry or external language model is used. AI answers are produced by a local language model (Ollama) on this machine.

2. Which data, for what purpose, and where is it processed?
- Source code and configuration (may contain test data or e-mail addresses): processed to find cryptography usage. Processed locally only; the analyzer sees your project read-only. It stays on your disk and Quancrypt does not copy it.
- Secrets in source code (passwords, private keys, tokens): not stored; they are detected locally and masked. However, text you type into the chat yourself is stored as written in the local chat history, even if it contains a secret; do not type secrets into the chat.
- Code snippets sent to the local language model: used to classify uncertain findings and answer questions. They go only to the local model on this machine and are not stored separately. However, the assistant''s answer may quote a code snippet, and answers are stored in the chat history.
- Findings, topology and migration plan: kept in the local core-service database to show the inventory and a risk-ordered plan, until you delete the project.
- Project identity (root path or git address): used to recognise the same project. The path or address is not stored; a one-way digest (HMAC-SHA256) computed with a secret key specific to this installation is stored. It is kept until you delete the project; the digest of a deleted project may remain in audit records, in anonymous events waiting to be sent or already sent (including the consent-withdrawal notice) and in the project reference of the agent database (see section 4). The folder name is also stored in the core database as the project''s display name.
- Chat texts: your questions and the assistant''s answers are kept in the local agent database to show the conversation history. Questions found to be out of scope also stay in this history. It is a local history; you can delete it (in this version deleting chats is done only through the service interface, the API).
- Scope decision: processed locally to check whether a question is within Quancrypt''s topic. The decision record holds coded fields such as the decision, confidence score, the deciding ring, processing time and language; the question text is not in this record (the question is in the chat history).

3. Processing that does not and does require consent
Analysis does not require consent. Scans, findings, topology and plan are kept only in the local database.

There are two separate, optional consents; both are off by default:
1. WAREHOUSE_ANALYTICS (analytics): Anonymous events derived from your project (coded fields such as algorithm family, usage context, priority, counts and version numbers; no file paths, source code or free text) are sent to the local analytics store (warehouse) and used in dashboards.
2. MODEL_TRAINING (model training): The same anonymous data is used to train local risk models.

You can continue without giving consent; analysis still works.

4. Withdrawing consent and deletion
- You can withdraw a consent at any time on the Settings screen.
- When you withdraw WAREHOUSE_ANALYTICS, events not yet sent in the core database are deleted; the agent''s pending scope-decision events are discarded after the consent is checked again before they would be sent. The deletion of this project''s records in the warehouse is requested.
- When you delete a project, the project''s records in the core database are deleted. Audit records made of the anonymous project digest and an action code, anonymous events waiting to be sent or already sent (including the consent-withdrawal notice) and the project reference in the agent database may remain. The chat history is in a separate local database and is not deleted automatically when a project is deleted; you need to delete the chat sessions separately.
- You can delete the chat history yourself (in this version only through the API).

5. Possible central use in the future (information)
In this prototype no data is sent to a central service. If a central service is added in the future, only anonymous, coded finding data (metadata instead of code) would be sent, and only with your consent; this notice would then be republished and your consent asked again.

6. Security
The interface is reachable only from this machine''s local address (127.0.0.1) and requires a random session key generated at every installation.',
    TIMESTAMPTZ '2026-10-19 00:00:00+00'
);
