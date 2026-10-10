package com.quancrypt.core.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.AuditEntry;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.ProjectKey;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** AuditLogWriter and AuditLogReader. */
public abstract class AuditPortsContract extends PortContract {

    @Test
    void entriesOfAProjectArePagedNewestFirst() {
        ProjectKey key = randomKey();
        AuditEntry registered = new AuditEntry(ids.next(), at(1), AuditAction.PROJECT_REGISTERED, Optional.of(key), Optional.empty(), CallerKind.UI);
        AuditEntry started = new AuditEntry(ids.next(), at(2), AuditAction.SCAN_STARTED, Optional.of(key), Optional.of(ids.next()), CallerKind.INTERNAL);
        AuditEntry other = new AuditEntry(ids.next(), at(3), AuditAction.PROJECT_REGISTERED, Optional.of(randomKey()), Optional.empty(), CallerKind.UI);
        AuditEntry relay = new AuditEntry(ids.next(), at(4), AuditAction.OUTBOX_EVENTS_RELAYED, Optional.empty(), Optional.empty(), CallerKind.INTERNAL);
        for (AuditEntry entry : new AuditEntry[] {registered, started, other, relay}) {
            ports.auditWriter().append(entry);
        }

        PageResult<AuditEntry> page = ports.auditReader().page(key, 0, 10);

        assertThat(page.items()).containsExactly(started, registered);
        assertThat(page.total()).isEqualTo(2);
        assertThat(ports.auditReader().page(key, 1, 1).items()).containsExactly(registered);
    }
}
