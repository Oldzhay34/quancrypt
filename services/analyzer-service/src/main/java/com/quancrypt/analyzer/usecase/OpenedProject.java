package com.quancrypt.analyzer.usecase;

import com.quancrypt.analyzer.domain.model.ProjectDescriptor;
import com.quancrypt.analyzer.port.outbound.SourceTree;

/** A project whose root was admitted and opened and whose build system is known. */
record OpenedProject(ProjectDescriptor descriptor, SourceTree tree) {
}
