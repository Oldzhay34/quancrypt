package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.domain.model.ScanArtifact;
import com.quancrypt.core.port.outbound.ProjectKeyHasher;
import java.nio.charset.StandardCharsets;

/** The project key is the SHA-256 of the identity here; the real adapter uses an HMAC with the salt. */
public final class Sha256ProjectKeyHasher implements ProjectKeyHasher {

    @Override
    public ProjectKey hash(String identity) {
        return new ProjectKey(ScanArtifact.sha256Hex(identity.getBytes(StandardCharsets.UTF_8)));
    }
}
