package com.quancrypt.analyzer.usecase;

import com.quancrypt.analyzer.domain.model.AllowedRoots;
import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.ProjectDescriptor;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.domain.policy.ProjectTypeDetector;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import com.quancrypt.analyzer.port.outbound.SourceTreeReader;
import java.util.Objects;

/** Admits a root, opens its source tree and detects the build system; shared by the project use cases. */
public final class ProjectOpener {

    private final AllowedRoots allowedRoots;
    private final SourceTreeReader reader;
    private final ProjectTypeDetector detector;

    public ProjectOpener(AllowedRoots allowedRoots, SourceTreeReader reader, ProjectTypeDetector detector) {
        this.allowedRoots = Objects.requireNonNull(allowedRoots, "allowedRoots");
        this.reader = Objects.requireNonNull(reader, "reader");
        this.detector = Objects.requireNonNull(detector, "detector");
    }

    OpenedProject open(String root) {
        AnalysisRoot admitted = Inputs.root(allowedRoots, root);
        return Failures.translate(() -> {
            SourceTree tree = reader.open(admitted);
            ProjectDescriptor descriptor = new ProjectDescriptor(admitted, detector.detect(name -> tree.exists(RelativePath.of(name))));
            return new OpenedProject(descriptor, tree);
        });
    }
}
