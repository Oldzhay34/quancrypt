---
id: netlestirme-protokolu
title: "Netleştirme protokolü: plan öncesi en fazla beş soru"
source_url: null
source_type: INTERNAL
version_tag: "Quancrypt proje dokümanı s.17"
applies_to: {}
language: tr
status: draft
---

Planlama agent'ı plan çıkarmadan önce, kodun yanıtlayamadığı en fazla beş soruyu sorar ve yanıtları yerel proje profiline kaydeder:

1. TLS nerede sonlanıyor: uygulamada mı, ingress'te mi, servis mesh'te mi, yük dengeleyicide mi?
2. Hedef JDK sürümüne yükseltme mümkün mü?
3. Hibrit grubu desteklemeyebilecek dış istemciler veya iş ortakları var mı?
4. FIPS, BDDK veya kurum politikası gibi bir uyum gereksinimi var mı?
5. Saha cihazlarının donanımı ve OpenSSL sürümü nedir?
