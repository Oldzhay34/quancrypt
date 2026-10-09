package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.AuditEntry;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.port.outbound.AuditLogWriter;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.IdGenerator;
import java.util.Optional;
import java.util.UUID;

/** Appends audit rows with the time and identifier of the moment (D-125). */
public final class AuditRecorder {

    private final AuditLogWriter writer;
    private final Clock clock;
    private final IdGenerator ids;

    public AuditRecorder(AuditLogWriter writer, Clock clock, IdGenerator ids) {
        this.writer = writer;
        this.clock = clock;
        this.ids = ids;
    }

    void record(AuditAction action, Optional<ProjectKey> projectKey, Optional<UUID> subjectId, CallerKind caller) {
        writer.append(new AuditEntry(ids.next(), clock.now(), action, projectKey, subjectId, caller));
    }
}
