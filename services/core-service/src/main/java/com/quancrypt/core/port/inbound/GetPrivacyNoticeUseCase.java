package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.PrivacyNoticeView;

/** Reads the latest privacy notice. */
public interface GetPrivacyNoticeUseCase {

    PrivacyNoticeView execute(GetPrivacyNoticeQuery input);
}
