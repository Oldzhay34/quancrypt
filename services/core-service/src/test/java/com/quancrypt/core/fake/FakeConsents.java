package com.quancrypt.core.fake;

import com.quancrypt.core.domain.exception.ConcurrentModificationException;
import com.quancrypt.core.domain.exception.DuplicateConsentException;
import com.quancrypt.core.domain.model.Consent;
import com.quancrypt.core.domain.model.ConsentType;
import com.quancrypt.core.port.outbound.ConsentLock;
import com.quancrypt.core.port.outbound.ConsentReader;
import com.quancrypt.core.port.outbound.ConsentWriter;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Consents with FOR SHARE locks, optimistic updates and the unique (project, type) rule. */
public final class FakeConsents implements ConsentLock, ConsentReader, ConsentWriter {

    private final InMemoryDatabase db;

    public FakeConsents(InMemoryDatabase db) {
        this.db = db;
    }

    @Override
    public Optional<Consent> share(UUID projectId, ConsentType type) {
        db.lockLog.add("consent:share");
        return find(projectId, type);
    }

    @Override
    public List<Consent> updateAll(UUID projectId) {
        db.lockLog.add("consent:updateAll");
        return list(projectId);
    }

    @Override
    public Optional<Consent> find(UUID projectId, ConsentType type) {
        return db.consents.values().stream().filter(c -> c.projectId().equals(projectId) && c.type() == type).findFirst();
    }

    @Override
    public List<Consent> list(UUID projectId) {
        return db.consents.values().stream().filter(c -> c.projectId().equals(projectId)).toList();
    }

    @Override
    public void insert(Consent consent) {
        if (find(consent.projectId(), consent.type()).isPresent()) {
            throw new DuplicateConsentException();
        }
        db.consents.put(consent.id(), consent);
    }

    @Override
    public void update(Consent updated, int expectedVersion) {
        Consent stored = db.consents.get(updated.id());
        if (stored == null || stored.version() != expectedVersion) {
            throw new ConcurrentModificationException("consent");
        }
        db.consents.put(updated.id(), updated);
    }
}
