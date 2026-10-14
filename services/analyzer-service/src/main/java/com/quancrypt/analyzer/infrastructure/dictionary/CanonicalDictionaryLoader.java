package com.quancrypt.analyzer.infrastructure.dictionary;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CanonicalDictionary;
import com.quancrypt.analyzer.domain.model.CanonicalEntry;
import com.quancrypt.analyzer.domain.model.CanonicalKind;
import com.quancrypt.analyzer.domain.model.UsageContext;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Optional;

/**
 * Loads the canonical dictionary from its CSV form (contracts/canonical_dictionary.csv, copied into the resources as
 * canonical-names.csv by the build). The file is part of the service, so a malformed row fails the start-up.
 */
public final class CanonicalDictionaryLoader {

    public static final String RESOURCE = "/canonical-names.csv";
    private static final String HEADER = "kind,raw,algorithm_family,mode,padding,hash,usage_context,key_size_bits";

    public CanonicalDictionary loadFromClasspath() {
        try (InputStream in = CanonicalDictionaryLoader.class.getResourceAsStream(RESOURCE)) {
            if (in == null) {
                throw new IllegalStateException("the canonical dictionary resource " + RESOURCE + " is missing");
            }
            return load(in);
        } catch (IOException e) {
            throw new UncheckedIOException("the canonical dictionary cannot be read", e);
        }
    }

    public CanonicalDictionary load(InputStream in) throws IOException {
        List<CanonicalEntry> entries = new ArrayList<>();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            String header = reader.readLine();
            if (!HEADER.equals(header)) {
                throw new IllegalStateException("the canonical dictionary has an unexpected header");
            }
            String line;
            int number = 1;
            while ((line = reader.readLine()) != null) {
                number++;
                if (line.isBlank()) {
                    continue;
                }
                entries.add(row(line, number));
            }
        }
        return new CanonicalDictionary(entries);
    }

    private static CanonicalEntry row(String line, int number) {
        String[] cells = line.split(",", -1);
        if (cells.length != 8) {
            throw new IllegalStateException("canonical dictionary line " + number + " does not have 8 columns");
        }
        try {
            return new CanonicalEntry(CanonicalKind.valueOf(cells[0].toUpperCase(Locale.ROOT)), cells[1],
                    optional(cells[2]).map(AlgorithmFamily::valueOf), optional(cells[3]), optional(cells[4]), optional(cells[5]),
                    optional(cells[6]).map(UsageContext::valueOf), optional(cells[7]).map(Integer::valueOf));
        } catch (IllegalArgumentException e) {
            throw new IllegalStateException("canonical dictionary line " + number + " is invalid", e);
        }
    }

    private static Optional<String> optional(String cell) {
        return cell.isEmpty() ? Optional.empty() : Optional.of(cell);
    }
}
