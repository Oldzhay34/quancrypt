# data-platform

Quancrypt veri platformu (Python 3.12, hexagonal, tek paket `quancrypt_data`). P6.1 ile gelen parça **ingest-api**'dir: core-service
ve agent-service outbox relay'lerinin gönderdiği olayları `warehouse_db`'nin iniş katmanına (`raw`) yazar. Korpus hattı (P6.2),
ön işleme (P6.4) ve warehouse (P6.5, P6.6) sonraki alt fazlardadır.

## ingest-api

- Kontrat: [`contracts/openapi/ingest-api.yaml`](../contracts/openapi/ingest-api.yaml). Tek komut: `POST /api/v1/events` (zarf dizisi,
  en çok 500 olay ve 8 MiB). Kimlik: `X-Internal-Token` (`INTERNAL_SERVICE_TOKEN`). Sağlık: `/health/liveness`, `/health/readiness`.
- Her zarf `contracts/schemas/events/<event_type>.json` şemasına göre doğrulanır. Şemaya uymayan kayıt reddedilmez, `quarantine.event`'e
  yazılır ve parti işlenmiş sayılır (relay tekrar göndermez). Yazma `event_id` ile idempotenttir.
- `consent_revoked` bir komut olayıdır: saklanmaz; o `project_key`'in `raw.event` ve `quarantine.event` satırlarını siler ve
  `ingest.ingest_audit`'e yazar (D-295d). Silinecek tablo listesi `ProjectKeyTableRegistry`'dedir; P6.4 ve P6.6 genişletir.
- Şema ve gerekçeleri: `docs/data/warehouse_raw-erd.md`. Saklama kuralı: `docs/data/retention.md`.

## Komutlar

| Komut | Ne yapar |
|---|---|
| `make verify` | ruff, mypy --strict, import-linter, pytest (birim, sözleşme ve gerçek PostgreSQL; Docker Desktop açık olmalı), domain+usecase kapsamı ≥ %75 |
| `make compile` | `requirements.in` → `requirements.txt` (`uv pip compile`) |
| `make run` | Servisi yerelde çalıştırır (`127.0.0.1:8084`); ortamda `WAREHOUSE_DB_*` ve `INTERNAL_SERVICE_TOKEN` gerekir |
| `make image` | Docker imajı (`ingest-api:1.0.0`); build bağlamı depo kökü |
| `make e2e` | Uçtan uca test (aşağıda); `make verify` içinde değildir |

## Uçtan uca test (`make e2e`)

core-service API'siyle proje kaydı, onay, QBank altın verisinden türetilmiş bulgular ve topoloji → core outbox → relay → ingest-api →
`raw.event`. Çalışan bir yığın ister. `.env`'e dokunmadan, rastgele sırlı geçici bir env dosyasıyla ve ayrı bir compose projesiyle:

```bash
# 1. geçici env dosyası (rastgele sırlar; .env kullanılmaz) ve yığın
docker compose -p quancrypt-p61 --env-file /yol/p61.env --profile app --profile data up -d --build postgres core-service ingest-api
# 2. test (aynı env dosyası kabuğa okunur)
set -a; . /yol/p61.env; set +a; make -C data-platform e2e
# 3. temizlik
docker compose -p quancrypt-p61 --env-file /yol/p61.env --profile app --profile data down -v
```

Env dosyasında `.env.example`'daki parola ve token anahtarları ile `OUTBOX_RELAY_ENABLED=true` ve
`INGEST_API_URL=http://ingest-api:8084/api/v1/events` bulunur. Test relay'i core-service'in iç ucu üzerinden tetikler, zamanlayıcı beklemez.

## Mimari

`api` → `facade` → `port.inbound` ← `usecase` → `port.outbound` ← `infrastructure`; `domain` merkezdedir (hexagonal-service skill'i).
Kurallar `pyproject.toml`'daki import-linter kontratlarıyla denetlenir. Kompozisyon kökü `infrastructure/container.py`; ASGI giriş
noktası `quancrypt_data.api.ingest:app` yalnızca onu çağırır. Migration'lar `migrations/` (Alembic, ileriye dönük) ve servis açılışında
migrator rolüyle uygulanır.
