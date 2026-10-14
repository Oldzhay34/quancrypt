package com.quancrypt.analyzer.infrastructure.plugin.javaspring.file;

import java.io.StringReader;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

/**
 * What one walk over a pom.xml yields: the dependencies, the properties and the Spring Boot version declared by the parent or
 * the Boot BOM. The file is read with a StAX reader that allows no DTD and no external entity; nothing is executed.
 */
final class MavenPom {

    private static final Set<String> LEAVES = Set.of("groupId", "artifactId", "version");
    private static final Pattern PROPERTY_REFERENCE = Pattern.compile("^\\$\\{([^}]+)}$");

    private final Map<String, String> properties;
    private final Optional<String> bootVersion;
    private final List<BuildDependency> dependencies;

    private MavenPom(Map<String, String> properties, Optional<String> bootVersion, List<BuildDependency> dependencies) {
        this.properties = Map.copyOf(properties);
        this.bootVersion = bootVersion;
        this.dependencies = List.copyOf(dependencies);
    }

    static MavenPom parse(String xml) throws XMLStreamException {
        Map<String, String> properties = new HashMap<>();
        List<BuildDependency> dependencies = new ArrayList<>();
        Optional<String> bootParent = Optional.empty();
        Optional<String> bootBom = Optional.empty();
        XMLStreamReader reader = reader(xml);
        List<String> path = new ArrayList<>();
        Map<String, String> fields = new HashMap<>();
        int dependencyLine = 0;
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.START_ELEMENT) {
                path.add(reader.getLocalName());
                if (reader.getLocalName().equals("dependency")) {
                    dependencyLine = reader.getLocation().getLineNumber();
                }
                if (path.size() == 3 && path.get(1).equals("properties")) {
                    properties.put(reader.getLocalName(), reader.getElementText());
                    path.remove(path.size() - 1);
                } else if (isLeafOfParentOrDependency(path) && LEAVES.contains(reader.getLocalName())) {
                    fields.put(path.get(path.size() - 2) + "/" + reader.getLocalName(), reader.getElementText());
                    path.remove(path.size() - 1);
                }
            } else if (event == XMLStreamConstants.END_ELEMENT) {
                String name = reader.getLocalName();
                if (name.equals("parent") && "spring-boot-starter-parent".equals(fields.get("parent/artifactId"))) {
                    bootParent = Optional.ofNullable(fields.get("parent/version"));
                }
                if (name.equals("dependency")) {
                    String artifact = fields.get("dependency/artifactId");
                    if ("spring-boot-dependencies".equals(artifact)) {
                        bootBom = Optional.ofNullable(fields.get("dependency/version"));
                    }
                    if (fields.containsKey("dependency/groupId") && artifact != null) {
                        dependencies.add(new BuildDependency(fields.get("dependency/groupId"), artifact,
                                Optional.ofNullable(fields.get("dependency/version")), dependencyLine));
                    }
                }
                if (name.equals("parent") || name.equals("dependency")) {
                    fields.clear();
                }
                path.remove(path.size() - 1);
            }
        }
        return new MavenPom(properties, bootParent.isPresent() ? bootParent : bootBom, dependencies);
    }

    /** The dependencies with property references like ${jjwt.version} replaced when the pom defines the property. */
    List<BuildDependency> dependencies() {
        return dependencies.stream().map(d -> new BuildDependency(d.group(), d.artifact(), d.version().map(this::resolve), d.line())).toList();
    }

    BuildVersions versions() {
        Optional<String> java = Optional.ofNullable(properties.get("java.version"))
                .or(() -> Optional.ofNullable(properties.get("maven.compiler.release")))
                .or(() -> Optional.ofNullable(properties.get("maven.compiler.source")))
                .flatMap(v -> BuildVersions.valid(resolve(v), true));
        Optional<String> boot = bootVersion.or(() -> Optional.ofNullable(properties.get("spring-boot.version")))
                .flatMap(v -> BuildVersions.valid(resolve(v), false));
        return new BuildVersions(java, boot);
    }

    private String resolve(String value) {
        Matcher matcher = PROPERTY_REFERENCE.matcher(value.strip());
        return matcher.matches() && properties.containsKey(matcher.group(1)) ? properties.get(matcher.group(1)).strip() : value.strip();
    }

    private static boolean isLeafOfParentOrDependency(List<String> path) {
        if (path.size() < 2) {
            return false;
        }
        String parent = path.get(path.size() - 2);
        return parent.equals("parent") || parent.equals("dependency");
    }

    private static XMLStreamReader reader(String xml) throws XMLStreamException {
        XMLInputFactory factory = XMLInputFactory.newFactory();
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        return factory.createXMLStreamReader(new StringReader(xml));
    }
}
