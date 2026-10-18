# Quancrypt CLI (`quancrypt`)

Proje kökünde tek komutla (`quancrypt init`) Quancrypt'i kurar: proje türünü tanır, yerel servisleri başlatır, projeyi
core-service'e kaydeder ve web arayüzünü yerel bir oturum token'ıyla açar (FR-01, FR-02). Python ve Typer ile yazılmıştır;
katmanlar hexagonal'dir (D-16): `api` Typer komutlarıdır.

## Kurulum

```bash
uv tool install ./apps/cli        # depo kökünden; komut adı: quancrypt
```

CLI, Quancrypt'in kurulu olduğu dizini (içinde `docker-compose.yml` ve doldurulmuş `.env` bulunan depo kökü) şu sırayla bulur:

1. `QUANCRYPT_HOME` ortam değişkeni (mutlak yol)
2. `~/.config/quancrypt/config.yaml` içindeki `home: /mutlak/yol` satırı

`.env` dosyasında `CHANGE_ME` kalmamış olmalıdır (kök `make check-env` ile aynı kural). CLI bunu denetlemez: yer tutucu parolalarla çalıştırırsanız servisler (örneğin postgres) kendileri başlamayı reddeder; önce `make check-env` çalıştırın. `QUANCRYPT_SESSION_TOKEN`
değerini CLI kendisi üretir ve servislere ortam değişkeni olarak verir; `.env`'dekinin yerine geçer.

Metinler varsayılan olarak Türkçedir; `QUANCRYPT_LANG=en` ile İngilizce olur.

## Komutlar

| Komut | Ne yapar |
|---|---|
| `quancrypt init [--path .] [--timeout 180]` | Aşağıdaki akış |
| `quancrypt up [--path .] [--timeout 180]` | Başlatılmış projenin servislerini kayıtlı token'la başlatır |
| `quancrypt down` | Servisleri durdurur (veritabanı volume'ü korunur) |
| `quancrypt status` | core, analyzer, agent ve web arayüzü sağlığı; gerekli bir servis hazır değilse çıkış kodu 1 |
| `quancrypt open [--path .]` | Web arayüzü adresini yazar (P5.2'ye kadar tarayıcı açılmaz, D-279) |

### `init` akışı

1. Kök doğrulanır: `pom.xml`, `build.gradle` veya `build.gradle.kts` olmalı; hiçbiri yoksa (veya hem Maven hem Gradle
   varsa) açıklayıcı hata verilir ve **hiçbir şey yazılmaz**.
2. Proje türü (Maven veya Gradle) tanınır.
3. Kullanıcı projesinde yalnızca `.quancrypt/` oluşturulur: `config.yaml` (proje adı, tür, oluşturulma zamanı, Quancrypt
   sürümü) ve `session.token` (32 bayt, base64url, izin 600). Başka hiçbir dosyaya dokunulmaz; `.gitignore` bile (D-272).
   `.gitignore` `.quancrypt/`'i kapsamıyorsa terminale uyarı ve eklenecek satır yazılır.
4. `docker compose --profile app up -d --wait` `PROJECT_ROOT` ve `QUANCRYPT_SESSION_TOKEN` ortam değişkenleriyle çalışır
   (argüman listesi, kabuk yok). İlk çalıştırmada imajlar derlenir ve bu birkaç dakika sürer.
5. core, analyzer ve agent servislerinin `/health/readiness` uçları hazır olana kadar beklenir (`--timeout`).
6. Proje core-service'e kaydedilir (`POST /api/v1/projects`, oturum token'ıyla; core yalnızca HMAC'ini saklar).
7. Web arayüzü adresi (`http://127.0.0.1:8080`, token'sız) yazılır. Web arayüzü P5.2'ye kadar yoktur; 8080'e yanıt veren
   bir şeye güvenilmez, o adres yoklanmaz ve **tarayıcı açılmaz** (D-279): token yalnızca Quancrypt'in kendi compose
   konteynerine verilebilir. P5.2'de `web-ui` konteyneri sağlıklıysa tarayıcı açılacaktır.
8. Terminale kısa bir KVKK notu yazılır; asıl aydınlatma metni ve onaylar web arayüzündedir.

`.quancrypt/` zaten varsa (D-273) `init` yeni bir token üretir, `config.yaml`'ı olduğu gibi bırakır ve servisleri yeni
token'la yeniden başlatır (eski token geçersiz olur). Proje core'da zaten kayıtlıysa bu bildirilir.

## Güvenlik

- Token `secrets` ile üretilir, dosyaya baştan 600 izinle ve atomik olarak yazılır; eski ve geniş izinli bir dosya yeniden
  kullanılmaz, değiştirilir. `.quancrypt/` veya `session.token` sembolik bağlantıysa yazma reddedilir.
- Token hiçbir komut satırı argümanında, log satırında, hata iletisinde veya terminal çıktısında yer almaz. Docker'a yalnızca
  alt sürecin ortam değişkeni olarak gider. Bu sürümde tarayıcıya hiçbir şey verilmez; P5.2'de URL parçası (`#token=`) olarak verilecek ve oradaki arayüz
  parçayı okuduktan sonra adres çubuğundan silecektir (`history.replaceState`, ILERIDE).
- Yalnızca `127.0.0.1` adresleri çağrılır; ortam proxy'si kullanılmaz ve yönlendirme izlenmez.
- **WSL notu:** proje bir Windows sürücüsündeyse (`/mnt/c/...`) dosya sistemi izinleri desteklemeyebilir; `chmod 600` etkisiz
  kalır. CLI bunu algılar ve uyarır. Projeyi Linux dosya sistemine (`~/...`) taşıyın.

## Bilinen sınırlar

- Aynı anda tek proje çalışır: analyzer-service `PROJECT_ROOT`'u salt okunur bağlar. Başka bir projede `init` servisleri o
  projeyle yeniden oluşturur.
- Token yenilenince compose üç servisi yeniden yaratır. Yeni token compose başlamadan diske yazıldığından, ikinci `init` servis başlatmada başarısız olursa dosyadaki token ayakta kalan servislerinkiyle uyuşmaz; `quancrypt init` ile tamamlayın.

## Geliştirme

```bash
make verify        # ruff, mypy --strict, import-linter, pytest (birim, sözleşme, mimari), coverage (domain+usecase >= %75)
make integration   # QBank kopyasında init uçtan uca; Docker ve QUANCRYPT_HOME gerekir (aşağıya bakın)
make compile       # requirements.in -> requirements.txt (uv pip compile)
```

Entegrasyon testi (`tests/integration/test_init_qbank.py`) QBank ödeme servisinin geçici bir kopyasında gerçek `docker
compose` ile `init` çalıştırır; 8080-8083 portları boş olmalıdır. Web arayüzü henüz olmadığından 8080'de testin kendi
küçük sunucusu durur; CLI'nin ona güvenmediği ve tarayıcı açmadığı da bununla sınanır. Önkoşullar eksikse test başarısız olur, atlanmaz:

```bash
QUANCRYPT_HOME=/depo/yolu make integration
```
