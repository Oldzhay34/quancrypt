package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.ClarificationAnswer;
import com.quancrypt.core.domain.model.ClarificationQuestion;
import com.quancrypt.core.port.outbound.ClarificationReader;
import com.quancrypt.core.port.outbound.ClarificationWriter;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Clarification answers, one per project and question. */
public final class FakeClarifications implements ClarificationReader, ClarificationWriter {

    private final InMemoryDatabase db;

    public FakeClarifications(InMemoryDatabase db) {
        this.db = db;
    }

    @Override
    public List<ClarificationAnswer> list(UUID projectId) {
        return db.answers.getOrDefault(projectId, Map.of()).entrySet().stream()
                .sorted(Map.Entry.comparingByKey()).map(Map.Entry::getValue).toList();
    }

    @Override
    public void upsertAll(UUID projectId, List<ClarificationAnswer> answers) {
        Map<ClarificationQuestion, ClarificationAnswer> stored = db.answers.computeIfAbsent(projectId, k -> new HashMap<>());
        answers.forEach(a -> stored.put(a.question(), a));
    }
}
