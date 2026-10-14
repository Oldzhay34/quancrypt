package com.quancrypt.analyzer.infrastructure.plugin.javaspring.file;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CryptoDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.DetectionSink;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileSupport;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import java.util.Locale;
import java.util.Optional;

/**
 * Keystore files ({@code .p12}, {@code .pfx}, {@code .jks}, ...): only their presence and type are reported. The content
 * is never opened (D-19), so the algorithm is UNKNOWN and the priority comes from the keystore rule of the table.
 */
public final class KeystoreFileDetector implements CryptoDetector {

    public static final String ID = "keystore.file";

    @Override
    public String detectorId() {
        return ID;
    }

    @Override
    public boolean appliesTo(ProjectFile file) {
        return file.kind() == FileKind.KEYSTORE;
    }

    @Override
    public void detect(ProjectIndex index, FileContext context, DetectionSink sink) {
        ProjectFile file = context.file();
        String name = file.name();
        String extension = name.substring(name.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT);
        String type = switch (extension) {
            case "p12", "pfx" -> "PKCS12";
            case "jks" -> "JKS";
            case "jceks" -> "JCEKS";
            case "bks" -> "BKS";
            default -> "keystore";
        };
        CryptoAlgorithm algorithm = new CryptoAlgorithm(AlgorithmFamily.UNKNOWN, type + " keystore", Optional.empty(), Optional.empty(),
                Optional.empty(), Optional.empty());
        sink.add(FileSupport.wholeFile(file, algorithm, UsageContext.KEYSTORE, 1.0, ID, null));
    }
}
