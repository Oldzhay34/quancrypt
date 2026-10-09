package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.PrivacyNotice;
import com.quancrypt.core.port.outbound.PrivacyNoticeReader;
import java.util.Comparator;
import java.util.Optional;

/** Privacy notices. */
public final class FakeNotices implements PrivacyNoticeReader {

    private final InMemoryDatabase db;

    public FakeNotices(InMemoryDatabase db) {
        this.db = db;
    }

    @Override
    public Optional<PrivacyNotice> latest() {
        return db.notices.stream().max(Comparator.comparingInt(PrivacyNotice::version));
    }
}
