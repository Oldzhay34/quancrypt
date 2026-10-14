package com.quancrypt.analyzer.infrastructure.cbom;

import com.quancrypt.analyzer.domain.model.Cbom;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.ProjectDescriptor;
import com.quancrypt.analyzer.port.outbound.CbomWriter;
import com.quancrypt.analyzer.port.outbound.Clock;
import com.quancrypt.analyzer.port.outbound.IdGenerator;
import java.util.Date;
import java.util.List;
import java.util.Objects;
import org.cyclonedx.Version;
import org.cyclonedx.exception.GeneratorException;
import org.cyclonedx.generators.BomGeneratorFactory;
import org.cyclonedx.model.Bom;
import org.cyclonedx.model.Component;
import org.cyclonedx.model.Metadata;
import org.cyclonedx.model.metadata.ToolInformation;

/**
 * Writes the CycloneDX 1.6 CBOM of an analysis (D-195) with cyclonedx-core-java. The document names no project: the
 * analyzed directory's name could carry a customer or a person's name, and the findings already carry every path (D-202).
 * The serial number and the time come from ports, so the same usages give the same document in a test.
 */
public final class CycloneDxCbomWriter implements CbomWriter {

    static final String SPEC_VERSION = "1.6";
    private static final String TOOL_NAME = "quancrypt-analyzer-service";

    private final Clock clock;
    private final IdGenerator ids;
    private final String toolVersion;

    public CycloneDxCbomWriter(Clock clock, IdGenerator ids, String toolVersion) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.ids = Objects.requireNonNull(ids, "ids");
        this.toolVersion = Objects.requireNonNull(toolVersion, "toolVersion");
    }

    @Override
    public Cbom write(ProjectDescriptor project, List<CryptoUsage> usages) {
        ComponentCatalog catalog = new ComponentCatalog();
        usages.forEach(catalog::add);
        Bom bom = new Bom();
        bom.setSerialNumber("urn:uuid:" + ids.newId());
        bom.setVersion(1);
        Metadata metadata = new Metadata();
        metadata.setTimestamp(Date.from(clock.now()));
        Component tool = new Component();
        tool.setType(Component.Type.APPLICATION);
        tool.setName(TOOL_NAME);
        tool.setVersion(toolVersion);
        ToolInformation tools = new ToolInformation();
        tools.setComponents(List.of(tool));
        metadata.setToolChoice(tools);
        bom.setMetadata(metadata);
        bom.setComponents(catalog.components());
        try {
            return new Cbom(SPEC_VERSION, BomGeneratorFactory.createJson(Version.VERSION_16, bom).toJsonString());
        } catch (GeneratorException e) {
            throw new IllegalStateException("the CBOM could not be written", e);
        }
    }
}
