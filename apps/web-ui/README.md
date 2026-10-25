# apps/web-ui

Quancrypt web arayüzü: React + Vite + TypeScript, feature tabanlı (D-15). P5.2 kapsamı: iskelet, oturum anahtarı, TR/EN,
KVKK aydınlatma ve onay akışı, ayarlar, düzen. P5.3 kapsamı: sohbet ve netleştirme ekranı (ilk tarama özeti, soru sorma,
kanıt çipleri, ret kartı, netleştirme formu, durdurma, geçmişi silme). P5.4 kapsamı: envanter (filtreler, CBOM indirme),
topoloji (Cytoscape.js grafiği, lejant, bağlantı paneli) ve plan (riske göre maddeler, rapor, Markdown indirme, yazdırma/PDF,
madde onayı).

## Çalıştırma

Arayüz yalnızca oturum anahtarıyla açılır. Anahtar `quancrypt init` ile üretilir ve projenizdeki
`.quancrypt/session.token` dosyasındadır. Compose ile (`app` profili) şu adreste çalışır:

```
http://127.0.0.1:8080/#token=<.quancrypt/session.token içeriği>
```

Anahtar adres çubuğundaki `#` parçasından okunur, bellekte ve `sessionStorage`'da tutulur ve parça adres çubuğundan hemen silinir.
Anahtar olmadan açılırsa açıklayıcı bir ekran, servisler 401 dönerse "oturum geçersiz" ekranı gösterilir. (CLI'nin tarayıcıyı
kendiliğinden açması bu sürümde yoktur, D-286.)

## Yapı

```
src/app/       yönlendirici, sağlayıcılar, düzen, geçitler (proje ve onay)
src/features/  chat/ consent/ inventory/ plan/ settings/ topology/
src/shared/    api/ auth/ i18n/ project/ session/ ui/
```

- Sohbet yanıtları ve ilk tarama sunucu olayları (SSE) olarak gelir. `EventSource` `Authorization` başlığı gönderemediği için
  `src/shared/api/sse.ts` `fetch` gövdesini okur ve olayları kendisi ayrıştırır (satır sonu olarak LF, CRLF ve CR, çok satırlı `data`, yorum
  satırları; olay başına 1 MiB sınırı). Olay türleri `features/chat/events.ts` içinde çalışma zamanında doğrulanır.
- Sohbet ekranı yanıtı düz metin olarak gösterir (HTML veya markdown asla). Kanıt çiplerinde yalnızca `https:` bilgi tabanı
  kaynakları bağlantı olur; `dosya:satır` ve araç çağrısı kimlikleri düz metindir.

- Bileşenler yalnızca sunum yapar; veri erişimi feature'ın `api.ts` ve `hooks.ts` dosyalarındadır (TanStack Query).
- Katman kuralları ESLint ile denetlenir: `shared` hiçbir feature veya `app` import etmez; bir feature başka bir feature'a yalnızca
  `index.ts` üzerinden ulaşır ve `app` import etmez.
- API tipleri `contracts/openapi/*.yaml` dosyalarından üretilir (`make gen-api`); üretilen dosyalar `src/shared/api/generated/`
  altındadır ve commit'lenir.
- Üç ekran (envanter, topoloji, plan) projenin en yeni tamamlanmış taramasını gösterir. Plan raporu (`text/markdown`) küçük bir
  okuyucuyla (`features/plan/markdown.ts`) çizilir: yalnızca başlık, liste, tablo ve ters bölü kaçışları; HTML, bağlantı ve vurgu
  yoktur. "Yazdır / PDF" tarayıcının yazdırma penceresini açar (menü ve düğmeler yazdırmada gizlenir, D-15).
- Topoloji kenar rengi, kenara bağlı bulguların algoritma ailesinden istemcide türetilir (D-293a); renk tek işaret değildir: her
  durumun kendi çizgi kalınlığı ve ok biçimi, lejantta ve tabloda adı vardır.
- Aydınlatma metni sunucudan düz metin olarak gelir ve düz metin olarak gösterilir (HTML olarak asla).

## Komutlar

```bash
make verify   # prettier, eslint, tsc --noEmit, vitest (npm run verify)
make run      # Vite geliştirme sunucusu (127.0.0.1:8080)
make image    # nginx imajı: web-ui:1.0.0
make gen-api  # OpenAPI tiplerini yeniden üretir
```

Node sürümü `.nvmrc` içindedir (`docs/VERSIONS.md`). `.npmrc` içindeki `legacy-peer-deps=true`, `openapi-typescript` 7.13'ün
`typescript ^5` peer bağımlılığı ile TypeScript 6.0.3'ün (D-42) çakışması yüzünden gereklidir; üretim çıktısı etkilenmez.

## Güvenlik

- nginx `USER 10001` ile çalışır. Başlıklar: `Content-Security-Policy` (`connect-src` yalnızca `http://127.0.0.1:8081`,
  `http://127.0.0.1:8083` ve (Dashboard bağlantısının yoklaması için) `http://127.0.0.1:8088`, `frame-ancestors 'none'`), `X-Content-Type-Options`, `Referrer-Policy: no-referrer`.
- Yalnızca `GET` ve `HEAD` kabul edilir. Dış kaynak (CDN, yazı tipi) yoktur.
- Anahtar yalnızca `Authorization: Bearer` başlığında gider; URL'ye, loga veya hata iletisine yazılmaz.
- `localStorage`'da yalnızca üç kişisel olmayan bilgi durur: dil seçimi (`quancrypt.lang`), "ilk çalıştırma görüldü"
  işareti (`consentSeen:<projectId>:<noticeVersion>`, D-288) ve proje başına sohbet oturumunun kimliği
  (`chatSession:<projectId>`, rastgele UUID; D-291c). Oturum anahtarı ve seçili proje `sessionStorage`'dadır.
- Kalan risk: tarayıcının genel geçmişi veya otomatik tamamlaması ilk açılan `#token=` adresini saklayabilir (fragment
  yaklaşımının doğası). Anahtar her `quancrypt init`'te yenilenir (D-273).
- nginx dışındaki katman kuralları: modülden dışarı çıkan göreli içe aktarma ESLint ile yasaktır (D-290c).
