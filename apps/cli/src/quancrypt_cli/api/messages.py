"""The texts of the CLI in Turkish and English (CLAUDE.md section 8). The language comes from `QUANCRYPT_LANG`."""

from __future__ import annotations

Language = str  # "tr" or "en"
DEFAULT_LANGUAGE = "tr"

_TEXTS: dict[str, dict[str, str]] = {
    "tr": {
        "starting": "Servisler başlatılıyor (ilk çalıştırmada imajlar derlenir; birkaç dakika sürebilir)...",
        "init.done": "Quancrypt hazır: {name} ({kind})",
        "services": "Servisler:",
        "service.ok": "hazır",
        "service.bad": "hazır değil",
        "registered.new": "Proje core-service'e kaydedildi.",
        "registered.known": "Proje core-service'te zaten kayıtlıydı.",
        "token.renewed": "Yeni oturum token'ı üretildi; eski token geçersiz.",
        "token.unprotected": "Uyarı: bu dosya sistemi dosya izinlerini desteklemiyor (örneğin WSL'de Windows sürücüsü); "
        ".quancrypt/session.token dosyası yalnızca sahibine kapatılamadı. Projeyi Linux dosya sistemine taşıyın.",
        # TODO(P5.1-1): web UI address text; P5.2 opens the browser once the compose-owned web-ui is healthy (D-279).
        "ui.address": "Web arayüzü adresi: {address} (web arayüzü P5.2'de gelir; tarayıcı bu sürümde açılmaz).",
        "gitignore.advice": "Öneri: .gitignore dosyanız .quancrypt/ dizinini kapsamıyor (oturum token'ı orada). "
        "Şu satırı kendiniz ekleyin: {line}",
        "kvkk": "KVKK notu: analiz tamamen bu makinede yapılır, hiçbir veri makinenizden çıkmaz. Warehouse analitiği ve "
        "model eğitimi için olay paylaşımı varsayılan olarak kapalıdır; aydınlatma metni ve onaylar web arayüzündedir.",
        "up.done": "Servisler çalışıyor.",
        "down.done": "Servisler durduruldu (veritabanı volume'ü korunur).",
        "status.ok": "Gerekli tüm servisler hazır.",
        "status.bad": "Hazır olmayan gerekli servis var.",
        "error": "Hata: {text}",
        "not-a-directory": "Verilen yol bir dizin değil.",
        "unreadable": "Dizin okunamadı (izin yok mu?).",
        "no-build-file": "Bu dizin bir Maven veya Gradle proje kökü değil: pom.xml, build.gradle veya build.gradle.kts yok. "
        "Komutu proje kökünde çalıştırın veya --path verin.",
        "ambiguous": "Dizinde hem Maven (pom.xml) hem Gradle (build.gradle) dosyası var; proje türü belirlenemedi.",
        "not-initialized": "Proje henüz başlatılmamış: önce `quancrypt init` çalıştırın.",
        "compose-failed": "docker compose çalışmadı: {detail}",
        "services-not-ready": "Servisler zamanında hazır olmadı: {detail}. `docker compose logs` ile bakın.",
        "registration-failed": "Proje core-service'e kaydedilemedi ({detail}). Servisler çalışıyor; `quancrypt init` ile tekrar deneyin.",
        "state-error": ".quancrypt/ okunamadı veya yazılamadı: {detail}. Dosyayı silip `quancrypt init` ile yeniden oluşturabilirsiniz.",
        "install-not-found": "Quancrypt kurulum dizini bulunamadı: {detail}",
        "unexpected": "Beklenmeyen hata ({detail}).",
    },
    "en": {
        "starting": "Starting the services (the first run builds the images and can take several minutes)...",
        "init.done": "Quancrypt is ready: {name} ({kind})",
        "services": "Services:",
        "service.ok": "ready",
        "service.bad": "not ready",
        "registered.new": "The project was registered in core-service.",
        "registered.known": "The project was already registered in core-service.",
        "token.renewed": "A new session token was created; the old token is no longer valid.",
        "token.unprotected": "Warning: this file system does not support file permissions (for example a Windows drive in "
        "WSL); .quancrypt/session.token could not be made owner-only. Move the project to a Linux file system.",
        "ui.address": "Web UI address: {address} (the web UI arrives in P5.2; no browser is opened in this version).",
        "gitignore.advice": "Advice: your .gitignore does not cover .quancrypt/ (the session token is there). "
        "Add this line yourself: {line}",
        "kvkk": "Privacy note: the analysis runs entirely on this machine and no data leaves it. Sharing events for "
        "warehouse analytics and model training is off by default; the privacy notice and the consents are in the web UI.",
        "up.done": "The services are running.",
        "down.done": "The services were stopped (the database volume is kept).",
        "status.ok": "All required services are ready.",
        "status.bad": "A required service is not ready.",
        "error": "Error: {text}",
        "not-a-directory": "The given path is not a directory.",
        "unreadable": "The directory could not be read (no permission?).",
        "no-build-file": "This directory is not a Maven or Gradle project root: there is no pom.xml, build.gradle or "
        "build.gradle.kts. Run the command in the project root or pass --path.",
        "ambiguous": "The directory holds both a Maven (pom.xml) and a Gradle (build.gradle) file; the project type is unclear.",
        "not-initialized": "The project is not initialised yet: run `quancrypt init` first.",
        "compose-failed": "docker compose failed: {detail}",
        "services-not-ready": "The services were not ready in time: {detail}. Look at `docker compose logs`.",
        "registration-failed": "The project could not be registered in core-service ({detail}). The services are running; "
        "run `quancrypt init` again.",
        "state-error": ".quancrypt/ could not be read or written: {detail}. You can delete the file and run `quancrypt init` again.",
        "install-not-found": "The Quancrypt installation directory was not found: {detail}",
        "unexpected": "Unexpected error ({detail}).",
    },
}


def language_from(value: str | None) -> Language:
    return value if value in _TEXTS else DEFAULT_LANGUAGE


def text(language: Language, key: str, **values: str) -> str:
    return _TEXTS[language_from(language)][key].format(**values)
