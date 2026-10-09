package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.RecordFindingsResult;

/** Records findings of a running scan. */
public interface RecordFindingsUseCase {

    RecordFindingsResult execute(RecordFindingsCommand input);
}
