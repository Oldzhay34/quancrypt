package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.FindingDetail;
import com.quancrypt.core.domain.model.PageResult;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Reads findings; the scan is reached through the source file. */
public interface FindingReader {

    Optional<FindingDetail> find(UUID findingId);

    PageResult<FindingDetail> page(UUID scanId, FindingFilter filter, int page, int size);

    int countByScan(UUID scanId);

    List<FindingDetail> listByScan(UUID scanId);

    FindingStats stats(UUID scanId);
}
