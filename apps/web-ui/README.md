# apps/web-ui

Quancrypt web arayüzü: React + Vite + TypeScript, feature tabanlı (D-15). P5.2 kapsamı: iskelet, oturum anahtarı, TR/EN,
KVKK aydınlatma ve onay akışı, ayarlar, düzen. Sohbet, envanter, topoloji ve plan ekranlarının içi P5.3 ve P5.4'tedir
(şimdilik yer tutucu).

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
src/features/  consent/ settings/ (chat, inventory, topology, plan: yer tutucu)
src/shared/    api/ auth/ i18n/ project/ session/ ui/
```

- Bileşenler yalnızca sunum yapar; veri erişimi feature'ın `api.ts` ve `hooks.ts` dosyalarındadır (TanStack Query).
- Katman kuralları ESLint ile denetlenir: `shared` hiçbir feature veya `app` import etmez; bir feature başka bir feature'a yalnızca
  `index.ts` üzerinden ulaşır ve `app` import etmez.
- API tipleri `contracts/openapi/*.yaml` dosyalarından üretilir (`make gen-api`); üretilen dosyalar `src/shared/api/generated/`
  altındadır ve commit'lenir.
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

- nginx `USER 10001` ile çalışır. Başlıklar: `Content-Security-Policy` (`connect-src` yalnızca `http://127.0.0.1:8081` ve
  `http://127.0.0.1:8083`, `frame-ancestors 'none'`), `X-Content-Type-Options`, `Referrer-Policy: no-referrer`.
- Yalnızca `GET` ve `HEAD` kabul edilir. Dış kaynak (CDN, yazı tipi) yoktur.
- Anahtar yalnızca `Authorization: Bearer` başlığında gider; URL'ye, loga veya hata iletisine yazılmaz.
- `localStorage`'da yalnızca iki kişisel olmayan bilgi durur: dil seçimi (`quancrypt.lang`) ve "ilk çalıştırma görüldü"
  işareti (`consentSeen:<projectId>:<noticeVersion>`, D-288). Oturum anahtarı ve seçili proje `sessionStorage`'dadır.
- Kalan risk: tarayıcının genel geçmişi veya otomatik tamamlaması ilk açılan `#token=` adresini saklayabilir (fragment
  yaklaşımının doğası). Anahtar her `quancrypt init`'te yenilenir (D-273).
- nginx dışındaki katman kuralları: modülden dışarı çıkan göreli içe aktarma ESLint ile yasaktır (D-290c).
