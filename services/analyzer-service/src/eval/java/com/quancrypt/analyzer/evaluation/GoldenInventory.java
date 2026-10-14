package com.quancrypt.analyzer.evaluation;

import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;

/** Reads the QBank golden inventory (a repository file: plain data only, no object construction). */
public final class GoldenInventory {

    private GoldenInventory() {
    }

    public static List<GoldenEntry> load(Path file) throws IOException {
        try (Reader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            Object document = new Yaml(new SafeConstructor(new LoaderOptions())).load(reader);
            Object entries = ((Map<?, ?>) document).get("entries");
            List<GoldenEntry> result = new ArrayList<>();
            for (Object item : (List<?>) entries) {
                Map<?, ?> row = (Map<?, ?>) item;
                result.add(new GoldenEntry(String.valueOf(row.get("file")), String.valueOf(row.get("symbol")),
                        String.valueOf(row.get("algorithm_family")), String.valueOf(row.get("usage_context")),
                        String.valueOf(row.get("location_kind")), String.valueOf(row.get("priority"))));
            }
            return List.copyOf(result);
        }
    }
}
