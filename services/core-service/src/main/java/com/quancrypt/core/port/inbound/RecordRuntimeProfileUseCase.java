package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.RuntimeProfileView;

/** Records a runtime profile when the versions changed. */
public interface RecordRuntimeProfileUseCase {

    RuntimeProfileView execute(RecordRuntimeProfileCommand input);
}
