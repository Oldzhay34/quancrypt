# Quancrypt

Quancrypt, bir Spring Boot projesindeki RSA tabanlı kriptografiyi bulan, servisler ve saha cihazları arasındaki bağlantıları haritalayan ve ML-KEM/ML-DSA hibrit geçişi için riske göre sıralı bir plan üreten, tamamen yerelde çalışan bir agent platformudur. Bu repo, platformun 10 haftalık okul prototipidir (Aşama 1). Hafta 1, 5 Ekim 2026 haftasıdır; teslim 13 Aralık 2026'dır.

## Repo haritası

```
quancrypt/
├── CLAUDE.md, Makefile, docker-compose.yml, .env.example
├── contracts/          OpenAPI 3.1 ve JSON Schema (tek doğruluk kaynağı)
├── services/
│   ├── core-service/       Java, hexagonal, core_db (3NF): proje, onay, tarama, bulgu, plan, denetim
│   ├── analyzer-service/   Java, hexagonal, durumsuz: kripto keşfi, CBOM, topoloji
│   ├── agent-service/      Python, görseldeki yapı, agent_db (3NF + pgvector)
│   └── transform-service/  Java, hexagonal (Faz 8, opsiyonel; yazma yetkisi yalnız bunda)
├── apps/
│   ├── web-ui/             React + Vite + TypeScript
│   └── cli/                Python Typer, `quancrypt init`
├── data-platform/      Python: ingest-api, korpus hattı, ön işleme, dbt projesi (warehouse_db)
├── ml/                 Python: etiketleme, eğitim, mining, MLflow, ONNX
├── reference-system/   QBank demo sistemi (bilerek RSA'lı) ve saha cihazı simülatörü
├── qkd-sim/            Q# BB84 ve ETSI 014 sahte anahtar sunucusu (Faz 8, opsiyonel)
├── infra/              postgres init betikleri, mosquitto ve benzeri yapılandırmalar
├── models/             ONNX model çıktıları (git'e girmez; volume)
└── docs/               decisions/, prompts/, gates/, reference/, adr/, PROGRESS.md, VERSIONS.md
```

Bu haritadaki dizinlerin ve dosyaların çoğu henüz yoktur; ilgili faz çalıştıkça oluşturulur. Güncel durum `docs/PROGRESS.md` dosyasındadır.

## Claude Code kiti nasıl kullanılır

Repo, Claude Code ile faz faz kurulur. Kit şunları içerir:

- `CLAUDE.md`: her oturumda yüklenen çalışma sözleşmesi
- `.claude/skills/`: 13 skill
- `.claude/agents/`: 3 inceleme subagent'ı
- `.claude/settings.json`: oturumu plan modunda açan izin ayarları
- `docs/decisions/DECISIONS.md`: bağlayıcı kararlar
- `docs/PROGRESS.md`: alt faz durumları
- `docs/gates/`: onay kapıları
- `docs/prompts/`: faz promptları

Çalışma döngüsü:

1. Repo kökünde `claude` komutuyla Claude Code'u başlatın.
2. Bir faz promptunu yapıştırın ya da `/run-phase <faz-id>` yazın (örneğin `/run-phase P0.2`). `run-phase` skill'i promptu `docs/prompts/<faz-id>.md` dosyasından okur.
3. Claude Code plan modunda anladığını ve sorularını sunar. Planı onaylayınca uygular.
4. Alt faz bitince `phase-gate` skill'i doğrulamayı çalıştırır, raporu yazar ve durur.
5. Raporu kontrol edip onay verdikten sonra commit'i siz atarsınız.

Komutlar için `make help` çalıştırın.
