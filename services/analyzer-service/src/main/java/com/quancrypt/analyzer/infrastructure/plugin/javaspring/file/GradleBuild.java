package com.quancrypt.analyzer.infrastructure.plugin.javaspring.file;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Reads build.gradle and build.gradle.kts with patterns; nothing of the script is evaluated. */
final class GradleBuild {

    private static final Pattern GAV = Pattern.compile("[\"']([A-Za-z0-9_.-]+):([A-Za-z0-9_.-]+)(?::([A-Za-z0-9_.${}-]+))?[\"']");
    private static final Pattern JAVA = Pattern.compile(
            "(?:JavaLanguageVersion\\.of\\(|jvmToolchain\\(|JavaVersion\\.VERSION_|sourceCompatibility\\s*=\\s*[\"']?|release(?:\\.set\\(|\\s*=\\s*))"
                    + "(\\d{1,2}(?:_\\d{1,2})?)");
    private static final Pattern BOOT = Pattern.compile(
            "(?:id\\s*\\(?\\s*[\"']org\\.springframework\\.boot[\"']\\s*\\)?\\s*version\\s*\\(?\\s*[\"']"
                    + "|org\\.springframework\\.boot:spring-boot[a-z-]*:|springBootVersion\\s*=\\s*[\"'])([0-9A-Za-z._+-]+)");

    private GradleBuild() {
    }

    static List<BuildDependency> dependencies(List<String> lines) {
        List<BuildDependency> found = new ArrayList<>();
        for (int i = 0; i < lines.size(); i++) {
            Matcher matcher = GAV.matcher(lines.get(i));
            while (matcher.find()) {
                found.add(new BuildDependency(matcher.group(1), matcher.group(2), Optional.ofNullable(matcher.group(3)), i + 1));
            }
        }
        return found;
    }

    static BuildVersions versions(List<String> lines) {
        Optional<String> java = Optional.empty();
        Optional<String> boot = Optional.empty();
        for (String line : lines) {
            String code = line.strip();
            if (code.startsWith("//")) {
                continue;
            }
            Matcher javaMatcher = JAVA.matcher(code);
            if (java.isEmpty() && javaMatcher.find()) {
                java = BuildVersions.valid(javaMatcher.group(1).replace('_', '.'), true);
            }
            Matcher bootMatcher = BOOT.matcher(code);
            if (boot.isEmpty() && bootMatcher.find()) {
                boot = BuildVersions.valid(bootMatcher.group(1), false);
            }
        }
        return new BuildVersions(java, boot);
    }
}
