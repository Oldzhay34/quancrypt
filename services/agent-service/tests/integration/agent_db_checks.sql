-- Behaviour checks of the agent_db schema as the migration builds it (P4.2). Run by tests/integration/test_schema.py with
-- psql as the superuser against an empty set of entity tables (the lookup tables hold the migration data).
-- Every check prints "NOTICE:  ok   <label>" or "NOTICE:  FAIL <label>"; the test fails on any FAIL.
\set ON_ERROR_STOP on
\set QUIET on
SET client_min_messages = notice;

CREATE FUNCTION pg_temp.expect(label text, stmt text, want_state text) RETURNS void LANGUAGE plpgsql AS $f$
BEGIN
  BEGIN
    EXECUTE stmt;
    RAISE NOTICE 'FAIL % (no error, wanted %)', label, want_state;
  EXCEPTION WHEN OTHERS THEN
    IF SQLSTATE = want_state THEN RAISE NOTICE 'ok   %', label;
    ELSE RAISE NOTICE 'FAIL % (got %, wanted %: %)', label, SQLSTATE, want_state, SQLERRM; END IF;
  END;
END $f$;

CREATE FUNCTION pg_temp.assert(label text, cond boolean) RETURNS void LANGUAGE plpgsql AS $f$
BEGIN
  IF cond THEN RAISE NOTICE 'ok   %', label; ELSE RAISE NOTICE 'FAIL %', label; END IF;
END $f$;

CREATE FUNCTION pg_temp.vec(seed int) RETURNS vector LANGUAGE sql AS $f$
  SELECT ('[' || array_to_string(ARRAY(SELECT ((seed * 7 + i * 13) % 100 + 1) / 100.0 FROM generate_series(1, 768) i), ',') || ']')::vector
$f$;

-- ---- şema sayımı
SELECT pg_temp.assert('31 tablo (17 lookup + 14 varlık)',
  (SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
   AND table_name <> 'alembic_version') = 31);
SELECT pg_temp.assert('ENUM tipi yok', (SELECT count(*) FROM pg_type WHERE typtype = 'e') = 0);
SELECT pg_temp.assert('JSON kolonu yalnız outbox_event.payload',
  (SELECT string_agg(table_name || '.' || column_name, ',') FROM information_schema.columns
   WHERE table_schema = 'public' AND data_type IN ('json', 'jsonb')) = 'outbox_event.payload');
SELECT pg_temp.assert('vector kolonu yalnız kb_chunk.embedding',
  (SELECT string_agg(table_name || '.' || column_name, ',') FROM information_schema.columns
   WHERE table_schema = 'public' AND udt_name = 'vector') = 'kb_chunk.embedding');

-- ---- örnek veri
INSERT INTO project_ref VALUES ('00000000-0000-0000-0000-000000000001', repeat('a', 64), now());
INSERT INTO chat_session VALUES ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'tr', now());
INSERT INTO chat_message VALUES ('20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 1, 'USER', 'soru', now());
INSERT INTO chat_message VALUES ('20000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', 2, 'ASSISTANT', 'yanıt', now());
INSERT INTO message_evidence VALUES ('20000000-0000-0000-0000-000000000002', 1, 'KNOWLEDGE_BASE', 'https://openjdk.org/jeps/496', 'JEP 496');
INSERT INTO message_evidence VALUES ('20000000-0000-0000-0000-000000000002', 2, 'CODE_LOCATION', 'src/Main.java:12', NULL);
INSERT INTO agent_run VALUES ('30000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'MESSAGE', repeat('1', 32), 'COMPLETED', now(), now());
INSERT INTO agent_step VALUES ('40000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', 1, 'INPUT_GUARD', NULL, 'SUCCEEDED', 5, 0, 0, now());
INSERT INTO agent_step VALUES ('40000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000001', 2, 'ACT', 'DISCOVERY', 'SUCCEEDED', 50, 0, 0, now());
INSERT INTO tool_call VALUES ('50000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000002', 'ANALYZER', 'SUCCEEDED', 40, now());
INSERT INTO tool_call VALUES ('50000000-0000-0000-0000-000000000002', '40000000-0000-0000-0000-000000000002', 'UNKNOWN', 'DENIED', 1, now());
INSERT INTO scope_decision VALUES ('60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'ALLOW', 0.9100, 'SCOPE_CLASSIFIER', 12, 'tr', now());
INSERT INTO scope_decision VALUES ('60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', 'DENY', NULL, 'RULE_FILTER', 1, 'tr', now());
INSERT INTO scope_decision VALUES ('60000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000001', 'ALLOW', NULL, 'LLM_SELF_CHECK', 900, 'en', now());
INSERT INTO outbox_event VALUES ('70000000-0000-0000-0000-000000000001', 'scope_decision', 1, repeat('a', 64), now(),
  '{"decision":"ALLOW","confidence":0.91,"deciding_ring":"SCOPE_CLASSIFIER","latency_ms":12,"language":"tr"}', NULL);
INSERT INTO idempotency_record VALUES ('anahtar-1', 'CREATE_SESSION', repeat('b', 64), 201, '10000000-0000-0000-0000-000000000001', now());

-- ---- project_ref: project_key benzersiz değil (silinip yeniden kaydedilen proje aynı HMAC ile yeni project_id alır)
INSERT INTO project_ref VALUES ('00000000-0000-0000-0000-000000000002', repeat('a', 64), now());
SELECT pg_temp.assert('project_key iki project_id için aynı olabilir',
  (SELECT count(*) FROM project_ref WHERE project_key = repeat('a', 64)) = 2);
DELETE FROM project_ref WHERE project_id = '00000000-0000-0000-0000-000000000002';

-- ---- kısıt ihlalleri
SELECT pg_temp.expect('project_key büyük harf', $$INSERT INTO project_ref VALUES (gen_random_uuid(), repeat('A', 64), now())$$, '23514');
SELECT pg_temp.expect('project_id tekrar', $$INSERT INTO project_ref VALUES ('00000000-0000-0000-0000-000000000001', repeat('c', 64), now())$$, '23505');
SELECT pg_temp.expect('oturum: var olmayan proje', $$INSERT INTO chat_session VALUES (gen_random_uuid(), gen_random_uuid(), 'tr', now())$$, '23503');
SELECT pg_temp.expect('oturum: var olmayan dil', $$INSERT INTO chat_session VALUES (gen_random_uuid(), '00000000-0000-0000-0000-000000000001', 'de', now())$$, '23503');
SELECT pg_temp.expect('mesaj ordinal 0', $$INSERT INTO chat_message VALUES (gen_random_uuid(), '10000000-0000-0000-0000-000000000001', 0, 'USER', 'x', now())$$, '23514');
SELECT pg_temp.expect('mesaj boş içerik', $$INSERT INTO chat_message VALUES (gen_random_uuid(), '10000000-0000-0000-0000-000000000001', 3, 'USER', '', now())$$, '23514');
SELECT pg_temp.expect('mesaj ordinal tekrarı', $$INSERT INTO chat_message VALUES (gen_random_uuid(), '10000000-0000-0000-0000-000000000001', 1, 'USER', 'x', now())$$, '23505');
SELECT pg_temp.expect('mesaj geçersiz rol', $$INSERT INTO chat_message VALUES (gen_random_uuid(), '10000000-0000-0000-0000-000000000001', 3, 'SYSTEM', 'x', now())$$, '23503');
SELECT pg_temp.expect('kanıt: KB dışı türde sürüm etiketi', $$INSERT INTO message_evidence VALUES ('20000000-0000-0000-0000-000000000002', 3, 'TOOL_CALL', 'c1', 'v1')$$, '23514');
SELECT pg_temp.expect('run RUNNING ama finished_at dolu', $$INSERT INTO agent_run VALUES (gen_random_uuid(), NULL, 'MESSAGE', repeat('2', 32), 'RUNNING', now(), now())$$, '23514');
SELECT pg_temp.expect('run COMPLETED ama finished_at boş', $$INSERT INTO agent_run VALUES (gen_random_uuid(), NULL, 'MESSAGE', repeat('2', 32), 'COMPLETED', now(), NULL)$$, '23514');
SELECT pg_temp.expect('run trace_id büyük harf', $$INSERT INTO agent_run VALUES (gen_random_uuid(), NULL, 'MESSAGE', repeat('A', 32), 'RUNNING', now(), NULL)$$, '23514');
SELECT pg_temp.expect('run trace_id serbest metin', $$INSERT INTO agent_run VALUES (gen_random_uuid(), NULL, 'MESSAGE', 'ad.soyad_tc12345678901xxxxxxxxxx', 'RUNNING', now(), NULL)$$, '23514');
SELECT pg_temp.expect('run trace_id kısa', $$INSERT INTO agent_run VALUES (gen_random_uuid(), NULL, 'MESSAGE', 'abc', 'RUNNING', now(), NULL)$$, '23514');
SELECT pg_temp.expect('adım: iş akışı düğümü agent taşıyamaz', $$INSERT INTO agent_step VALUES (gen_random_uuid(), '30000000-0000-0000-0000-000000000001', 3, 'ROUTE', 'SUPERVISOR', 'SUCCEEDED', 1, 0, 0, now())$$, '23514');
SELECT pg_temp.expect('adım: ANSWER düğümü agent taşıyamaz', $$INSERT INTO agent_step VALUES (gen_random_uuid(), '30000000-0000-0000-0000-000000000001', 3, 'ANSWER', 'SUPERVISOR', 'SUCCEEDED', 1, 0, 0, now())$$, '23514');
SELECT pg_temp.expect('adım: yaşam döngüsü adımı agent ister', $$INSERT INTO agent_step VALUES (gen_random_uuid(), '30000000-0000-0000-0000-000000000001', 3, 'PLAN', NULL, 'SUCCEEDED', 1, 0, 0, now())$$, '23514');
SELECT pg_temp.expect('adım ordinal tekrarı', $$INSERT INTO agent_step VALUES (gen_random_uuid(), '30000000-0000-0000-0000-000000000001', 1, 'PLAN', 'PLANNER', 'SUCCEEDED', 1, 0, 0, now())$$, '23505');
SELECT pg_temp.expect('adım negatif token', $$INSERT INTO agent_step VALUES (gen_random_uuid(), '30000000-0000-0000-0000-000000000001', 4, 'PLAN', 'PLANNER', 'SUCCEEDED', 1, -1, 0, now())$$, '23514');
SELECT pg_temp.expect('araç çağrısı geçersiz araç', $$INSERT INTO tool_call VALUES (gen_random_uuid(), '40000000-0000-0000-0000-000000000002', 'WEB_SEARCH', 'SUCCEEDED', 1, now())$$, '23503');
SELECT pg_temp.expect('araç UNKNOWN yalnız DENIED olabilir', $$INSERT INTO tool_call VALUES (gen_random_uuid(), '40000000-0000-0000-0000-000000000002', 'UNKNOWN', 'SUCCEEDED', 1, now())$$, '23514');
SELECT pg_temp.expect('karar: FAIL_CLOSED ALLOW olamaz', $$INSERT INTO scope_decision VALUES (gen_random_uuid(), NULL, 'ALLOW', NULL, 'FAIL_CLOSED', 1, 'tr', now())$$, '23514');
SELECT pg_temp.expect('karar: kural filtresi güven taşımaz', $$INSERT INTO scope_decision VALUES (gen_random_uuid(), NULL, 'DENY', 0.5, 'RULE_FILTER', 1, 'tr', now())$$, '23514');
SELECT pg_temp.expect('karar: FAIL_CLOSED güven taşımaz', $$INSERT INTO scope_decision VALUES (gen_random_uuid(), NULL, 'DENY', 0.5, 'FAIL_CLOSED', 1, 'tr', now())$$, '23514');
SELECT pg_temp.expect('karar: LLM öz-denetimi güven taşımaz', $$INSERT INTO scope_decision VALUES (gen_random_uuid(), NULL, 'ALLOW', 0.5, 'LLM_SELF_CHECK', 1, 'tr', now())$$, '23514');
SELECT pg_temp.expect('karar: sınıflandırıcı güven taşımak zorunda', $$INSERT INTO scope_decision VALUES (gen_random_uuid(), NULL, 'ALLOW', NULL, 'SCOPE_CLASSIFIER', 1, 'tr', now())$$, '23514');
SELECT pg_temp.expect('karar: güven 1.5', $$INSERT INTO scope_decision VALUES (gen_random_uuid(), NULL, 'ALLOW', 1.5, 'SCOPE_CLASSIFIER', 1, 'tr', now())$$, '23514');
SELECT pg_temp.expect('karar: güven -0.1', $$INSERT INTO scope_decision VALUES (gen_random_uuid(), NULL, 'ALLOW', -0.1, 'SCOPE_CLASSIFIER', 1, 'tr', now())$$, '23514');
SELECT pg_temp.expect('karar: negatif gecikme', $$INSERT INTO scope_decision VALUES (gen_random_uuid(), NULL, 'ALLOW', 0.5, 'SCOPE_CLASSIFIER', -1, 'tr', now())$$, '23514');
SELECT pg_temp.expect('outbox: payload dizi', $$INSERT INTO outbox_event VALUES (gen_random_uuid(), 'scope_decision', 1, repeat('a', 64), now(), '[]', NULL)$$, '23514');
SELECT pg_temp.expect('outbox: bilinmeyen olay türü', $$INSERT INTO outbox_event VALUES (gen_random_uuid(), 'finding_detected', 1, repeat('a', 64), now(), '{}', NULL)$$, '23503');
SELECT pg_temp.expect('outbox: kısa project_key', $$INSERT INTO outbox_event VALUES (gen_random_uuid(), 'scope_decision', 1, 'abc', now(), '{}', NULL)$$, '23514');
SELECT pg_temp.expect('outbox: yayın zamanı olay zamanından önce', $$INSERT INTO outbox_event VALUES (gen_random_uuid(), 'scope_decision', 1, repeat('a', 64), now(), '{}', now() - interval '1 hour')$$, '23514');
SELECT pg_temp.expect('idempotency anahtar tekrarı', $$INSERT INTO idempotency_record VALUES ('k1','CREATE_SESSION', repeat('b',64), 201, NULL, now()), ('k1','CREATE_SESSION', repeat('b',64), 201, NULL, now())$$, '23505');
SELECT pg_temp.expect('idempotency: yalnız boşluk anahtarı', $$INSERT INTO idempotency_record VALUES ('   ','CREATE_SESSION', repeat('b',64), 201, NULL, now())$$, '23514');
SELECT pg_temp.expect('idempotency: 129 karakterlik anahtar', $$INSERT INTO idempotency_record VALUES (repeat('k', 129),'CREATE_SESSION', repeat('b',64), 201, NULL, now())$$, '22001');
INSERT INTO idempotency_record VALUES ('anahtar-1', 'ANSWER_CLARIFICATIONS', repeat('b', 64), 200, NULL, now());
SELECT pg_temp.assert('aynı anahtar farklı işlemde serbest', true);

INSERT INTO kb_document VALUES ('80000000-0000-0000-0000-000000000001', 'jep-496', 'JEP 496 ML-KEM', 'https://openjdk.org/jeps/496', 'JEP', 'JDK 24', 'en', repeat('c', 64), 'embeddinggemma:latest', 1200, 150, now());
INSERT INTO kb_document VALUES ('80000000-0000-0000-0000-000000000002', 'tls-genel', 'TLS genel', 'https://docs.spring.io/spring-boot/reference/features/ssl.html', 'VENDOR_DOC', 'Boot 3.x', 'tr', repeat('d', 64), 'embeddinggemma:latest', 1200, 150, now());
INSERT INTO kb_document VALUES ('80000000-0000-0000-0000-000000000003', 'boot-ssl-bundle', 'SSL bundle', 'https://docs.spring.io/spring-boot/reference/features/ssl.html', 'VENDOR_DOC', 'Boot 3.5', 'tr', repeat('e', 64), 'embeddinggemma:latest', 1200, 150, now());
INSERT INTO kb_document VALUES ('80000000-0000-0000-0000-000000000004', 'strateji-tablosu', 'Strateji tablosu', NULL, 'INTERNAL', 'Quancrypt proje dokümanı', 'tr', repeat('f', 64), 'embeddinggemma:latest', 1200, 150, now());
SELECT pg_temp.assert('INTERNAL not source_url NULL olabilir', (SELECT source_url IS NULL FROM kb_document WHERE doc_key = 'strateji-tablosu'));
SELECT pg_temp.expect('belge: JEP türünde source_url NULL', $$INSERT INTO kb_document VALUES (gen_random_uuid(), 'x0', 't', NULL, 'JEP', 'v', 'tr', repeat('c', 64), 'm', 1200, 150, now())$$, '23514');
SELECT pg_temp.expect('belge: http URL', $$INSERT INTO kb_document VALUES (gen_random_uuid(), 'x1', 't', 'http://x.org/a', 'JEP', 'v', 'tr', repeat('c', 64), 'm', 1200, 150, now())$$, '23514');
SELECT pg_temp.expect('belge: URL içinde sekme', $$INSERT INTO kb_document VALUES (gen_random_uuid(), 'x3', 't', E'https://x.org/a\tb', 'JEP', 'v', 'tr', repeat('c', 64), 'm', 1200, 150, now())$$, '23514');
SELECT pg_temp.expect('belge: URL içinde boşluk', $$INSERT INTO kb_document VALUES (gen_random_uuid(), 'x4', 't', 'https://x.org/a b', 'JEP', 'v', 'tr', repeat('c', 64), 'm', 1200, 150, now())$$, '23514');
SELECT pg_temp.expect('belge: URL 1025 karakter', $$INSERT INTO kb_document VALUES (gen_random_uuid(), 'x5', 't', 'https://x.org/' || repeat('a', 1011), 'JEP', 'v', 'tr', repeat('c', 64), 'm', 1200, 150, now())$$, '22001');
SELECT pg_temp.expect('belge: doc_key büyük harf', $$INSERT INTO kb_document VALUES (gen_random_uuid(), 'Bad', 't', 'https://x.org/a', 'JEP', 'v', 'tr', repeat('c', 64), 'm', 1200, 150, now())$$, '23514');
SELECT pg_temp.expect('belge: doc_key tekrar', $$INSERT INTO kb_document VALUES (gen_random_uuid(), 'jep-496', 't', 'https://x.org/a', 'JEP', 'v', 'tr', repeat('c', 64), 'm', 1200, 150, now())$$, '23505');
SELECT pg_temp.expect('belge: geçersiz kaynak türü', $$INSERT INTO kb_document VALUES (gen_random_uuid(), 'x2', 't', 'https://x.org/a', 'BLOG', 'v', 'tr', repeat('c', 64), 'm', 1200, 150, now())$$, '23503');
SELECT pg_temp.expect('belge: örtüşme parça boyutuna eşit', $$INSERT INTO kb_document VALUES (gen_random_uuid(), 'x6', 't', 'https://x.org/a', 'JEP', 'v', 'tr', repeat('c', 64), 'm', 100, 100, now())$$, '23514');
SELECT pg_temp.expect('belge: parça boyutu 0', $$INSERT INTO kb_document VALUES (gen_random_uuid(), 'x7', 't', 'https://x.org/a', 'JEP', 'v', 'tr', repeat('c', 64), 'm', 0, 0, now())$$, '23514');

INSERT INTO kb_document_applicability VALUES ('80000000-0000-0000-0000-000000000001', 'JAVA', 24, 0, NULL, NULL);
INSERT INTO kb_document_applicability VALUES ('80000000-0000-0000-0000-000000000003', 'SPRING_BOOT', 3, 5, NULL, NULL);
SELECT pg_temp.expect('uygulanabilirlik: sınırsız', $$INSERT INTO kb_document_applicability VALUES ('80000000-0000-0000-0000-000000000002', 'JAVA', NULL, NULL, NULL, NULL)$$, '23514');
SELECT pg_temp.expect('uygulanabilirlik: yarım çift', $$INSERT INTO kb_document_applicability VALUES ('80000000-0000-0000-0000-000000000002', 'JAVA', 17, NULL, NULL, NULL)$$, '23514');
SELECT pg_temp.expect('uygulanabilirlik: min > max', $$INSERT INTO kb_document_applicability VALUES ('80000000-0000-0000-0000-000000000002', 'SPRING_BOOT', 3, 6, 3, 5)$$, '23514');
SELECT pg_temp.expect('uygulanabilirlik: negatif', $$INSERT INTO kb_document_applicability VALUES ('80000000-0000-0000-0000-000000000002', 'JAVA', -1, 0, NULL, NULL)$$, '23514');
SELECT pg_temp.expect('uygulanabilirlik: Java için minor 0 olmalı', $$INSERT INTO kb_document_applicability VALUES ('80000000-0000-0000-0000-000000000002', 'JAVA', 17, 5, NULL, NULL)$$, '23514');
SELECT pg_temp.expect('uygulanabilirlik: aynı bileşen iki kez', $$INSERT INTO kb_document_applicability VALUES ('80000000-0000-0000-0000-000000000001', 'JAVA', 25, 0, NULL, NULL)$$, '23505');

INSERT INTO kb_chunk VALUES (gen_random_uuid(), '80000000-0000-0000-0000-000000000001', 1, 'ML-KEM JDK 24', pg_temp.vec(1));
INSERT INTO kb_chunk VALUES (gen_random_uuid(), '80000000-0000-0000-0000-000000000002', 1, 'TLS genel bilgi', pg_temp.vec(2));
INSERT INTO kb_chunk VALUES (gen_random_uuid(), '80000000-0000-0000-0000-000000000003', 1, 'SSL bundle PEM', pg_temp.vec(3));
SELECT pg_temp.expect('parça: yanlış vektör boyutu', $$INSERT INTO kb_chunk VALUES (gen_random_uuid(), '80000000-0000-0000-0000-000000000001', 2, 't', '[1,2,3]'::vector)$$, '22000');
SELECT pg_temp.expect('parça: ordinal tekrar', $$INSERT INTO kb_chunk VALUES (gen_random_uuid(), '80000000-0000-0000-0000-000000000001', 1, 't', pg_temp.vec(1))$$, '23505');
SELECT pg_temp.expect('parça: NULL vektör', $$INSERT INTO kb_chunk VALUES (gen_random_uuid(), '80000000-0000-0000-0000-000000000001', 3, 't', NULL)$$, '23502');
SELECT pg_temp.expect('parça: sıfır vektör', $$INSERT INTO kb_chunk VALUES (gen_random_uuid(), '80000000-0000-0000-0000-000000000001', 3, 't', array_fill(0, ARRAY[768])::vector)$$, '23514');

INSERT INTO audit_log VALUES ('90000000-0000-0000-0000-000000000001', now(), 'SESSION_DELETED', repeat('a', 64));
SELECT pg_temp.expect('denetim: geçersiz eylem', $$INSERT INTO audit_log VALUES (gen_random_uuid(), now(), 'NOPE', repeat('a', 64))$$, '23503');
SELECT pg_temp.expect('denetim: kısa project_key', $$INSERT INTO audit_log VALUES (gen_random_uuid(), now(), 'SESSION_DELETED', 'abc')$$, '23514');

-- ---- RESTRICT
SELECT pg_temp.expect('project_ref oturumu varken silinemez', $$DELETE FROM project_ref$$, '23503');
SELECT pg_temp.expect('kullanımdaki lookup silinemez', $$DELETE FROM scope_ring WHERE code = 'RULE_FILTER'$$, '23503');

-- ---- sorgular
SELECT pg_temp.assert('kosinüs: aynı vektör ilk sırada',
  (SELECT d.doc_key FROM kb_chunk c JOIN kb_document d ON d.id = c.document_id
   WHERE d.embedding_model = 'embeddinggemma:latest' ORDER BY c.embedding <=> pg_temp.vec(2) LIMIT 1) = 'tls-genel');

SELECT pg_temp.assert('sürüm filtresi: JDK 17 + Boot 3.2 JDK 24+ ve Boot 3.5+ belgelerini eler',
  (SELECT string_agg(d.doc_key, ',' ORDER BY d.doc_key) FROM kb_document d WHERE NOT EXISTS (
     SELECT 1 FROM kb_document_applicability a
     JOIN (VALUES ('JAVA', 17, 0), ('SPRING_BOOT', 3, 2)) rt(component, major, minor) ON rt.component = a.component
     WHERE a.document_id = d.id AND (
       (a.min_major IS NOT NULL AND (rt.major, rt.minor) < (a.min_major, a.min_minor))
       OR (a.max_major IS NOT NULL AND (rt.major, rt.minor) > (a.max_major, a.max_minor))))) = 'strateji-tablosu,tls-genel');
SELECT pg_temp.assert('sürüm filtresi: JDK 25 + Boot 3.5 hepsini bırakır',
  (SELECT count(*) FROM kb_document d WHERE NOT EXISTS (
     SELECT 1 FROM kb_document_applicability a
     JOIN (VALUES ('JAVA', 25, 0), ('SPRING_BOOT', 3, 5)) rt(component, major, minor) ON rt.component = a.component
     WHERE a.document_id = d.id AND (
       (a.min_major IS NOT NULL AND (rt.major, rt.minor) < (a.min_major, a.min_minor))
       OR (a.max_major IS NOT NULL AND (rt.major, rt.minor) > (a.max_major, a.max_minor))))) = 4);
SELECT pg_temp.assert('sürüm filtresi: Boot bilinmiyorsa yalnız Java filtrelenir',
  (SELECT string_agg(d.doc_key, ',' ORDER BY d.doc_key) FROM kb_document d WHERE NOT EXISTS (
     SELECT 1 FROM kb_document_applicability a
     JOIN (VALUES ('JAVA', 17, 0)) rt(component, major, minor) ON rt.component = a.component
     WHERE a.document_id = d.id AND (
       (a.min_major IS NOT NULL AND (rt.major, rt.minor) < (a.min_major, a.min_minor))
       OR (a.max_major IS NOT NULL AND (rt.major, rt.minor) > (a.max_major, a.max_minor))))) = 'boot-ssl-bundle,strateji-tablosu,tls-genel');

-- ---- DeleteSession: mesaj ve kanıt gider, denetim kalır (D-225); CREATE_SESSION idempotency kaydı da silinir (use case adımı)
DELETE FROM idempotency_record WHERE operation = 'CREATE_SESSION' AND resource_id = '10000000-0000-0000-0000-000000000001';
DELETE FROM chat_session WHERE id = '10000000-0000-0000-0000-000000000001';
SELECT pg_temp.assert('DeleteSession: mesajlar gitti', (SELECT count(*) FROM chat_message) = 0);
SELECT pg_temp.assert('DeleteSession: kanıtlar gitti', (SELECT count(*) FROM message_evidence) = 0);
SELECT pg_temp.assert('DeleteSession: run kaldı, session_id NULL',
  (SELECT count(*) FROM agent_run WHERE session_id IS NULL) = 1);
SELECT pg_temp.assert('DeleteSession: adım ve araç çağrıları kaldı',
  (SELECT count(*) FROM agent_step) = 2 AND (SELECT count(*) FROM tool_call) = 2);
SELECT pg_temp.assert('DeleteSession: kapsam kararları kaldı, session_id NULL',
  (SELECT count(*) FROM scope_decision WHERE session_id IS NULL) = 3);
SELECT pg_temp.assert('DeleteSession: outbox kaldı', (SELECT count(*) FROM outbox_event) = 1);
SELECT pg_temp.assert('DeleteSession: oturumun CREATE_SESSION kaydı gitti, başka işlem kaydı kaldı',
  (SELECT count(*) FROM idempotency_record WHERE operation = 'CREATE_SESSION') = 0
  AND (SELECT count(*) FROM idempotency_record WHERE operation = 'ANSWER_CLARIFICATIONS') = 1);
SELECT pg_temp.assert('DeleteSession: denetim kaydı kalıcı', (SELECT count(*) FROM audit_log) = 1);

-- ---- DeleteProjectData: oturum, project_ref ve o project_key'in bekleyen olayları gider; denetim kalır (D-232b)
INSERT INTO chat_session VALUES ('10000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'en', now());
INSERT INTO chat_message VALUES ('20000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000002', 1, 'USER', 'question', now());
INSERT INTO outbox_event VALUES ('70000000-0000-0000-0000-000000000002', 'scope_decision', 1, repeat('a', 64), now(), '{}', NULL);
INSERT INTO outbox_event VALUES ('70000000-0000-0000-0000-000000000003', 'scope_decision', 1, repeat('b', 64), now(), '{}', NULL);
DELETE FROM outbox_event WHERE project_key = (SELECT project_key FROM project_ref WHERE project_id = '00000000-0000-0000-0000-000000000001') AND published_at IS NULL;
DELETE FROM chat_session WHERE project_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM project_ref WHERE project_id = '00000000-0000-0000-0000-000000000001';
INSERT INTO audit_log VALUES ('90000000-0000-0000-0000-000000000002', now(), 'PROJECT_DATA_DELETED', repeat('a', 64));
SELECT pg_temp.assert('DeleteProjectData: oturum, mesaj ve project_ref gitti',
  (SELECT count(*) FROM chat_session) = 0 AND (SELECT count(*) FROM chat_message) = 0 AND (SELECT count(*) FROM project_ref) = 0);
SELECT pg_temp.assert('DeleteProjectData: yalnız o project_key olayları gitti',
  (SELECT count(*) FROM outbox_event) = 1 AND (SELECT project_key FROM outbox_event) = repeat('b', 64));
SELECT pg_temp.assert('DeleteProjectData: denetim satırları kaldı',
  (SELECT count(*) FROM agent_run) = 1 AND (SELECT count(*) FROM scope_decision) = 3 AND (SELECT count(*) FROM audit_log) = 2);

-- ---- zincir silmeler
DELETE FROM agent_run;
SELECT pg_temp.assert('agent_run silinince adım ve araç çağrıları da gider',
  (SELECT count(*) FROM agent_step) = 0 AND (SELECT count(*) FROM tool_call) = 0);
DELETE FROM kb_document WHERE doc_key = 'jep-496';
SELECT pg_temp.assert('kb_document silinince parça ve uygulanabilirlik gider',
  (SELECT count(*) FROM kb_chunk WHERE text = 'ML-KEM JDK 24') = 0
  AND (SELECT count(*) FROM kb_document_applicability WHERE component = 'JAVA') = 0);

-- ---- idempotent upsert deseni (build_index): önce DO NOTHING RETURNING, dönmezse kilitle ve karşılaştır
INSERT INTO kb_document VALUES ('80000000-0000-0000-0000-000000000009', 'upsert-ornek', 't', 'https://x.org/a', 'INTERNAL', 'v1', 'tr', repeat('1', 64), 'embeddinggemma:latest', 1200, 150, now())
  ON CONFLICT (doc_key) DO NOTHING;
SELECT pg_temp.assert('upsert: ilk ekleme satır döndürdü',
  (SELECT count(*) FROM kb_document WHERE doc_key = 'upsert-ornek') = 1);
INSERT INTO kb_document VALUES (gen_random_uuid(), 'upsert-ornek', 't', 'https://x.org/a', 'INTERNAL', 'v1', 'tr', repeat('1', 64), 'embeddinggemma:latest', 1200, 150, now())
  ON CONFLICT (doc_key) DO NOTHING;
SELECT pg_temp.assert('upsert: ikinci ekleme çakışır, tek satır ve id korunur',
  (SELECT count(*) FROM kb_document WHERE doc_key = 'upsert-ornek') = 1
  AND (SELECT id FROM kb_document WHERE doc_key = 'upsert-ornek') = '80000000-0000-0000-0000-000000000009');
