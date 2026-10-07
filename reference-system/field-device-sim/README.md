# field-device-sim

QBank saha terminali simülatörü (referans sistem): `terminal-001` gibi bir terminalin işlemlerini belirli aralıkla üretir ve MQTT üzerinden TLS ile, istemci sertifikasıyla (mTLS) `mosquitto` broker'ına yayımlar. Aynı kod PYNQ-Z2'de çalışır: **Python 3.10 sözdizimi sınırı** ve **tek çalışma zamanı bağımlılığı `paho-mqtt`** (D-111). Hexagonal düzen (D-05).

## Kullanım

```bash
python -m field_device_sim run --terminal-id terminal-001 --interval 5   # durdurulana kadar yayımlar
python -m field_device_sim healthcheck [--max-age 30]                    # son 30 sn içinde yayın yapıldıysa 0, yoksa 1
```

Her yayında rastgele ama tutarlı bir test işlemi üretilir (loga yalnızca `transactionId` yazılır): `accountId` demo hesaplardan (`acc-001`..`acc-003`), `amount` 1.00–500.00 TRY, `transactionId` UUIDv4, `occurredAt` UTC. `--seed` hesapları, tutarları ve kimlikleri tekrarlanabilir yapar (yalnızca test ve demo için). Mesaj `terminal/{terminalId}/transactions` konusuna QoS 1 ile gider ve kart verisi içermez; biçimi [`../contracts/terminal-transaction.schema.json`](../contracts/terminal-transaction.schema.json)'dadır. `SIGTERM` döngüyü bitirir ve bağlantıyı kapatır.

Broker erişilemezse simülatör çalışmaya devam eder, bağlantıyı yeniden dener ve başarısız yayını loglar; başarısız yayın sonradan kuyruktan gönderilmez. Yanıtı alınmayan (ama gönderilmiş) bir mesajı MQTT istemcisi yeniden bağlanınca tekrar gönderebilir; ödeme servisi aynı `transactionId`'yi yok sayar.

## Yapılandırma

Yalnızca ortam değişkenleriyle yapılandırılır; varsayılanlar yerel geliştirme içindir (imajda `Dockerfile` değerleri geçerlidir).

| Değişken | Varsayılan | Anlamı |
|---|---|---|
| `MQTT_BROKER_URL` | `ssl://localhost:8883` (imajda `ssl://mosquitto:8883`) | Broker; yalnızca `ssl://` kabul edilir |
| `QBANK_CERTS_DIR` | `../certs/out` (imajda `/certs`) | PEM dizini |
| `FIELD_DEVICE_SIM_STATUS_FILE` | geçici dizinde `field-device-sim.status` | Son başarılı yayının zamanı; sağlık kontrolü bunu okur |

Kullanılan dosyalar (`QBANK_CERTS_DIR` altında): `ca.crt.pem` (broker sertifikasını ve ana bilgisayar adını doğrular) ile terminalin kimliği `<terminal-id>.crt.pem` ve `<terminal-id>.key.pem` (örneğin `terminal-001`).

## Komutlar

```bash
make verify   # ruff, mypy --strict, import-linter, pytest + coverage; Docker Desktop açık olmalı
make verify PYTHON=3.10   # PYNQ-Z2 uyumlu en düşük sürümde aynı doğrulama (uv Python 3.10'u indirir)
make compile  # requirements.in dosyalarından requirements.txt dosyalarını derler (uv pip compile)
make run      # simülatörü yerelde çalıştırır
make image    # Docker imajı: field-device-sim:1.0.0
```

`make verify`: `ruff check`, `ruff format --check`, `mypy` (strict), `lint-imports` (katman kuralları), `pytest` (birim, `MessagePublisher` sözleşmesi, mimari ve entegrasyon) ve domain ile usecase için en az %75 satır kapsamı. Sözleşme ve entegrasyon testleri `eclipse-mosquitto:2.0.22` konteynerini `docker create/cp/start` ile gerçek `mosquitto.conf`, `acl` ve gerçek sertifikalarla başlatır; Docker yoksa testler atlanmaz, başarısız olur. Testler yayımlanan mesajın alanlarını sözleşme kurallarıyla elle denetler; JSON Schema ile asıl doğrulamayı ödeme servisi yapar (`make demo-smoke`).

## Katmanlar

```
api            argparse komutları (run, healthcheck); composition root'tan fabrika alır, infrastructure'ı tanımaz
facade         TerminalFacade (yayın), HealthFacade (sağlık), PublishFailedError
port.inbound   PublishTransactionUseCase, CheckHealthUseCase, komut/sonuç kayıtları, use case hataları
port.outbound  MessagePublisher, Clock, IdGenerator, RandomSource, StatusReporter
usecase        PublishTransaction, CheckHealth
domain         TerminalTransaction (yalnızca standart kütüphane)
infrastructure Paho MQTT adaptörü, sistem saati, UUID ve rastgele kaynak, durum dosyası, JSON log, ayarlar, container.py
```

`__main__.py` composition'ı yapar. Katman kuralları `pyproject.toml`'daki import-linter sözleşmelerinde ve `tests/architecture` altındadır.

## Bilerek kalan zayıflıklar

Zayıflıklar listesi: [`../README.md`](../README.md). Bu serviste: TLS bağlantısı RSA-2048 sertifikalı mTLS'tir. Anahtar değişim grubunu simülatör seçmez, Python'un OpenSSL'i seçer: imajdaki OpenSSL 3.5.7 Mosquitto'ya bağlanırken hibrit `X25519MLKEM768` sunar (P1.4'te aynı imajdaki OpenSSL 3.5.5 CLI ile *taklit edilerek* ölçüldü, `expected/topology.yaml`); sertifika ve imza yine RSA'dır. Terminal kimliği yalnızca sertifika ve broker ACL'iyle korunur.

## Docker

`Dockerfile` çok aşamalıdır (`python:3.12.15-slim`; bağımlılıklar `uv` ile `requirements.txt`'ten), `USER 10001` ile çalışır; sertifika ve anahtar imaja girmez, çalıştırırken yalnızca bu servisin dosyaları salt okunur bağlanır. `HEALTHCHECK` `python -m field_device_sim healthcheck` çağırır.
