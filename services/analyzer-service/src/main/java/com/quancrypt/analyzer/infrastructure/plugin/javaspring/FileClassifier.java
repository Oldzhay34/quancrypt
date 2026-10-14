package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.RelativePath;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Decides the kind of a project file from its path alone, and which directories hold generated output or tooling state
 * and are skipped (P3.2, D-190d). Files in test source sets are TEST_CODE whatever their kind (D-173).
 */
public final class FileClassifier {

    private static final Set<String> TOOL_DIRECTORIES = Set.of(".git", ".gradle", ".idea", "node_modules");
    private static final Set<String> OUTPUT_DIRECTORIES = Set.of("build", "target");
    private static final Set<String> BUILD_FILES = Set.of("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
            "settings.gradle.kts");
    private static final Pattern SPRING_CONFIG = Pattern.compile("(application|bootstrap)(-[A-Za-z0-9_.-]+)?\\.(ya?ml|properties)");
    private static final Pattern TEST_SOURCE_SET = Pattern.compile("(test|integrationTest|testFixtures|functionalTest)");
    private static final Set<String> KEYSTORES = Set.of("p12", "pfx", "jks", "jceks", "keystore", "bks");
    private static final Set<String> PEM_EXTENSIONS = Set.of("pem", "crt", "cer", "key");

    /** Whether a directory name at this place is skipped; {@code siblingNames} are the names in the directory's parent. */
    public boolean skipsDirectory(String name, Set<String> siblingNames) {
        if (TOOL_DIRECTORIES.contains(name)) {
            return true;
        }
        return OUTPUT_DIRECTORIES.contains(name) && siblingNames.stream().anyMatch(BUILD_FILES::contains);
    }

    public ProjectFile classify(RelativePath path) {
        List<String> segments = path.segments();
        String name = segments.get(segments.size() - 1);
        String lower = name.toLowerCase(Locale.ROOT);
        String extension = lower.contains(".") ? lower.substring(lower.lastIndexOf('.') + 1) : "";
        boolean test = inTestSourceSet(segments, name);
        if (lower.endsWith(".java")) {
            return new ProjectFile(path, FileKind.JAVA, test ? LocationKind.TEST_CODE : LocationKind.CODE);
        }
        if (SPRING_CONFIG.matcher(name).matches()) {
            FileKind kind = extension.equals("properties") ? FileKind.SPRING_PROPERTIES : FileKind.SPRING_YAML;
            return new ProjectFile(path, kind, test ? LocationKind.TEST_CODE : LocationKind.CONFIG);
        }
        if (lower.equals("mosquitto.conf") || (extension.equals("conf") && lower.startsWith("mosquitto"))) {
            return new ProjectFile(path, FileKind.MOSQUITTO_CONF, test ? LocationKind.TEST_CODE : LocationKind.CONFIG);
        }
        if (KEYSTORES.contains(extension)) {
            return new ProjectFile(path, FileKind.KEYSTORE, test ? LocationKind.TEST_CODE : LocationKind.KEYSTORE_FILE);
        }
        if (PEM_EXTENSIONS.contains(extension)) {
            return new ProjectFile(path, FileKind.PEM, test ? LocationKind.TEST_CODE : LocationKind.CERTIFICATE_FILE);
        }
        if (name.equals("pom.xml")) {
            return new ProjectFile(path, FileKind.POM, LocationKind.BUILD_FILE);
        }
        if (BUILD_FILES.contains(name)) {
            return new ProjectFile(path, FileKind.GRADLE, LocationKind.BUILD_FILE);
        }
        return new ProjectFile(path, FileKind.OTHER, LocationKind.CONFIG);
    }

    private static boolean inTestSourceSet(List<String> segments, String name) {
        for (int i = 0; i + 1 < segments.size() - 1; i++) {
            if (segments.get(i).equals("src") && TEST_SOURCE_SET.matcher(segments.get(i + 1)).matches()) {
                return true;
            }
        }
        return name.endsWith("Test.java") || name.endsWith("Tests.java") || name.endsWith("IT.java");
    }
}
