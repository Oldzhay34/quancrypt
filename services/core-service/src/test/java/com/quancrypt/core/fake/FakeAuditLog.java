package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.AuditEntry;
import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.port.outbound.AuditLogReader;
import com.quancrypt.core.port.outbound.AuditLogWriter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** The audit log; a test can make the next append fail to prove a rollback. */
public final class FakeAuditLog implements AuditLogWriter, AuditLogReader {

    private final InMemoryDatabase db;
    private boolean failNext;

    public FakeAuditLog(InMemoryDatabase db) {
        this.db = db;
    }

    public void failNextAppend() {
        this.failNext = true;
    }

    @Override
    public void append(AuditEntry entry) {
        if (failNext) {
            failNext = false;
            throw new IllegalStateException("injected audit failure");
        }
        db.audit.add(entry);
    }

    @Override
    public PageResult<AuditEntry> page(ProjectKey projectKey, int page, int size) {
        List<AuditEntry> all = new ArrayList<>(db.audit.stream().filter(e -> e.projectKey().filter(projectKey::equals).isPresent()).toList());
        Collections.reverse(all);
        return FakePaging.slice(all, page, size);
    }
}
