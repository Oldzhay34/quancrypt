---
id: kem-dem-kalibi
title: "Uygulama içi şifrelemede hedef kalıp: ML-KEM ile KEM-DEM"
source_url: null
source_type: INTERNAL
version_tag: "Quancrypt proje dokümanı s.19; crypto-domain"
applies_to:
  java: ">=24"
language: tr
status: draft
---

Uygulama içi RSA şifrelemenin hedef kalıbı KEM-DEM'dir: ML-KEM ile ortak sır kapsüllenir, sır HKDF ile bir AES-256-GCM anahtarına türetilir ve veri bu anahtarla şifrelenir. `javax.crypto.KEM` API'si JDK 21'den beri vardır; ML-KEM gerçeklemesi JDK 24 ile gelir.

```java
KeyPair kp = KeyPairGenerator.getInstance("ML-KEM").generateKeyPair();   // alıcı, bir kez
KEM kem = KEM.getInstance("ML-KEM");
KEM.Encapsulated e = kem.newEncapsulator(kp.getPublic()).encapsulate();  // gönderen
byte[] toReceiver = e.encapsulation();
SecretKey shared = e.key();            // HKDF ile AES-256-GCM anahtarına türetilir
SecretKey same = kem.newDecapsulator(kp.getPrivate()).decapsulate(toReceiver);
```

Kripto çevikliği için algoritmalar koda gömülmez; bir `CryptoPolicy` nesnesinin arkasına alınır. Böylece bir sonraki geçiş kod değişikliği değil, yapılandırma değişikliği olur.
