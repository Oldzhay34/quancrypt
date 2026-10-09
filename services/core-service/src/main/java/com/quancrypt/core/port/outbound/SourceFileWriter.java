package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.SourceFile;
import java.util.List;
import java.util.UUID;

/** Writes source files. */
public interface SourceFileWriter {

    void insertAll(List<SourceFile> files);

    /** Deletes files no finding and no call site points to (D-146); returns how many. */
    int deleteUnreferenced(UUID scanId);
}
