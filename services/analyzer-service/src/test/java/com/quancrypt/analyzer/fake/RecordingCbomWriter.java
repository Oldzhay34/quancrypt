package com.quancrypt.analyzer.fake;

import com.quancrypt.analyzer.domain.model.Cbom;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.ProjectDescriptor;
import com.quancrypt.analyzer.port.outbound.CbomWriter;
import java.util.List;

/** Test double of the CBOM writer: remembers the usages it was given and returns a fixed document. */
public final class RecordingCbomWriter implements CbomWriter {

    private List<CryptoUsage> written = List.of();

    public List<CryptoUsage> written() {
        return written;
    }

    @Override
    public Cbom write(ProjectDescriptor project, List<CryptoUsage> usages) {
        written = List.copyOf(usages);
        return new Cbom("1.6", "{\"bomFormat\":\"CycloneDX\",\"specVersion\":\"1.6\"}");
    }
}
