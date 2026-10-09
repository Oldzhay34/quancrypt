package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.PrivacyNotice;
import java.util.Optional;

/** Reads privacy notices. */
public interface PrivacyNoticeReader {

    Optional<PrivacyNotice> latest();
}
