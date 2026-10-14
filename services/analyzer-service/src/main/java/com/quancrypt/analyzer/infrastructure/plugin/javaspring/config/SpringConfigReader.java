package com.quancrypt.analyzer.infrastructure.plugin.javaspring.config;

import com.quancrypt.analyzer.domain.model.RelativePath;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.error.YAMLException;
import org.yaml.snakeyaml.nodes.MappingNode;
import org.yaml.snakeyaml.nodes.Node;
import org.yaml.snakeyaml.nodes.NodeTuple;
import org.yaml.snakeyaml.nodes.ScalarNode;
import org.yaml.snakeyaml.nodes.SequenceNode;

/**
 * Reads Spring Boot configuration files into flat properties: YAML (several documents, profile documents) and
 * .properties. YAML is only composed into a node tree, never turned into objects, so no type in the file is
 * instantiated; aliases, depth and size are limited.
 */
public final class SpringConfigReader {

    private static final int MAX_PROPERTIES = 20_000;
    private static final int MAX_DEPTH = 40;
    /** A flattened key longer than this is skipped with everything below it (an explicit key can be as long as the file). */
    private static final int MAX_KEY_LENGTH = 512;

    public List<ConfigProperty> yaml(RelativePath file, String text) {
        LoaderOptions options = new LoaderOptions();
        options.setMaxAliasesForCollections(20);
        options.setNestingDepthLimit(MAX_DEPTH);
        options.setCodePointLimit(2_000_000);
        options.setAllowDuplicateKeys(true);
        List<ConfigProperty> all = new ArrayList<>();
        try {
            for (Node document : new Yaml(options).composeAll(new StringReader(text))) {
                if (document instanceof MappingNode mapping) {
                    List<ConfigProperty> flat = new ArrayList<>();
                    flatten(file, "", mapping, flat, 0);
                    Optional<String> profile = profile(flat);
                    flat.forEach(property -> all.add(new ConfigProperty(property.file(), property.key(), property.value(), property.line(), profile)));
                }
                if (all.size() > MAX_PROPERTIES) {
                    break;
                }
            }
        } catch (YAMLException | StackOverflowError e) {
            return List.copyOf(all);
        }
        return List.copyOf(all);
    }

    public List<ConfigProperty> properties(RelativePath file, List<String> lines) {
        List<ConfigProperty> out = new ArrayList<>();
        for (int i = 0; i < lines.size() && out.size() < MAX_PROPERTIES; i++) {
            String line = lines.get(i).strip();
            if (line.isEmpty() || line.startsWith("#") || line.startsWith("!")) {
                continue;
            }
            int start = i + 1;
            StringBuilder logical = new StringBuilder(line);
            while (logical.charAt(logical.length() - 1) == '\\' && i + 1 < lines.size()) {
                logical.setLength(logical.length() - 1);
                logical.append(lines.get(++i).strip());
            }
            int separator = separatorIndex(logical);
            if (separator < 0) {
                continue;
            }
            String key = logical.substring(0, separator).strip();
            String value = logical.substring(separator + 1).strip();
            out.add(new ConfigProperty(file, key, value, start, Optional.empty()));
        }
        return List.copyOf(out);
    }

    private static int separatorIndex(CharSequence line) {
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (c == '=' || c == ':') {
                return i;
            }
        }
        return -1;
    }

    private void flatten(RelativePath file, String prefix, Node node, List<ConfigProperty> out, int depth) {
        if (depth > MAX_DEPTH || out.size() > MAX_PROPERTIES) {
            return;
        }
        if (node instanceof MappingNode mapping) {
            for (NodeTuple tuple : mapping.getValue()) {
                if (tuple.getKeyNode() instanceof ScalarNode key) {
                    if (prefix.length() + key.getValue().length() + 1 > MAX_KEY_LENGTH) {
                        continue;
                    }
                    String name = prefix.isEmpty() ? key.getValue() : prefix + "." + key.getValue();
                    flatten(file, name, tuple.getValueNode(), out, depth + 1);
                }
            }
        } else if (node instanceof SequenceNode sequence) {
            int index = 0;
            for (Node item : sequence.getValue()) {
                if (prefix.length() > MAX_KEY_LENGTH || out.size() > MAX_PROPERTIES) {
                    return;
                }
                flatten(file, prefix + "[" + index++ + "]", item, out, depth + 1);
            }
        } else if (node instanceof ScalarNode scalar && !prefix.isEmpty()) {
            out.add(new ConfigProperty(file, prefix, scalar.getValue(), scalar.getStartMark().getLine() + 1, Optional.empty()));
        }
    }

    private static Optional<String> profile(List<ConfigProperty> document) {
        return document.stream()
                .filter(p -> p.key().equals("spring.config.activate.on-profile") || p.key().equals("spring.profiles"))
                .map(ConfigProperty::value)
                .findFirst();
    }

    /** Whether the text could be a properties/YAML file we can read at all (guards against binary files). */
    public static boolean isText(String text) {
        return text.indexOf('\u0000') < 0;
    }
}
