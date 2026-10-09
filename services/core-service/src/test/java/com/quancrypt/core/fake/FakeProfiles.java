package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.RuntimeProfile;
import com.quancrypt.core.port.outbound.RuntimeProfileReader;
import com.quancrypt.core.port.outbound.RuntimeProfileWriter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** The runtime profile history of projects. */
public final class FakeProfiles implements RuntimeProfileReader, RuntimeProfileWriter {

    private final InMemoryDatabase db;

    public FakeProfiles(InMemoryDatabase db) {
        this.db = db;
    }

    @Override
    public Optional<RuntimeProfile> current(UUID projectId) {
        return db.profiles.getOrDefault(projectId, List.of()).stream().max(Comparator.comparingInt(RuntimeProfile::sequenceNo));
    }

    @Override
    public Optional<RuntimeProfile> bySequence(UUID projectId, int sequenceNo) {
        return db.profiles.getOrDefault(projectId, List.of()).stream().filter(p -> p.sequenceNo() == sequenceNo).findFirst();
    }

    @Override
    public void insert(UUID projectId, RuntimeProfile profile) {
        db.profiles.computeIfAbsent(projectId, k -> new ArrayList<>()).add(profile);
    }
}
