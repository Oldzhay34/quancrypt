package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.PrivacyNotice;
import com.quancrypt.core.port.inbound.GetPrivacyNoticeQuery;
import com.quancrypt.core.port.inbound.GetPrivacyNoticeUseCase;
import com.quancrypt.core.port.inbound.view.PrivacyNoticeView;
import com.quancrypt.core.port.outbound.PrivacyNoticeReader;

/** Reads the latest privacy notice. */
public final class GetPrivacyNoticeService implements GetPrivacyNoticeUseCase {

    private final PrivacyNoticeReader notices;

    public GetPrivacyNoticeService(PrivacyNoticeReader notices) {
        this.notices = notices;
    }

    @Override
    public PrivacyNoticeView execute(GetPrivacyNoticeQuery input) {
        PrivacyNotice notice = notices.latest().orElseThrow(() -> Fail.notFound("privacy notice"));
        return new PrivacyNoticeView(notice.version(), notice.textTr(), notice.textEn(), notice.publishedAt());
    }
}
