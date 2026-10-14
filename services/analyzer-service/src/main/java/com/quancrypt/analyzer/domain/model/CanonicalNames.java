package com.quancrypt.analyzer.domain.model;

import java.util.Optional;

/**
 * Resolves raw names found in code or configuration into {@link CanonicalEntry} codes. A name the dictionary does not
 * know resolves to nothing; detectors then report the family UNKNOWN at a low confidence.
 */
public final class CanonicalNames {

    private static final int MAX_RAW = 256;

    private final CanonicalDictionary dictionary;

    public CanonicalNames(CanonicalDictionary dictionary) {
        this.dictionary = dictionary;
    }

    /** A JCA transformation: an exact row wins, otherwise algorithm, mode and padding are looked up separately. */
    public Optional<CryptoAlgorithm> transformation(String raw) {
        Optional<CanonicalEntry> exact = dictionary.lookup(CanonicalKind.TRANSFORMATION, raw);
        if (exact.isPresent()) {
            return exact.map(entry -> algorithm(raw, entry));
        }
        if (raw.length() > MAX_RAW) {
            return Optional.empty();
        }
        String[] parts = raw.split("/", -1);
        Optional<CanonicalEntry> base = dictionary.lookup(CanonicalKind.ALGORITHM, parts[0]);
        if (base.isEmpty() || base.get().family().isEmpty()) {
            return Optional.empty();
        }
        Optional<CanonicalEntry> modeRow = parts.length > 1 ? dictionary.lookup(CanonicalKind.MODE, parts[1]) : Optional.empty();
        Optional<String> mode = parts.length > 1 ? modeRow.flatMap(CanonicalEntry::mode) : base.get().mode();
        Optional<CanonicalEntry> paddingRow = parts.length > 2 ? dictionary.lookup(CanonicalKind.PADDING, parts[2]) : Optional.empty();
        Optional<String> padding = paddingRow.isPresent() ? paddingRow.flatMap(CanonicalEntry::padding) : base.get().padding();
        Optional<String> hash = paddingRow.flatMap(CanonicalEntry::hash).or(() -> base.get().hash());
        if ((parts.length > 1 && mode.isEmpty()) || (parts.length > 2 && padding.isEmpty())) {
            return Optional.empty();
        }
        // JCA writes "ECB" in RSA transformations only as a name leftover; an asymmetric cipher has no mode.
        if (mode.filter("ECB"::equals).isPresent() && !isBlockCipher(base.get().family().get())) {
            mode = Optional.of("NONE");
        }
        String canonical = base.get().raw() + modeRow.map(row -> "/" + row.raw()).orElse("") + paddingRow.map(row -> "/" + row.raw()).orElse("");
        return Optional.of(new CryptoAlgorithm(base.get().family().get(), shown(raw, canonical), mode, padding, hash, base.get().keySizeBits()));
    }

    /** A row of the given kind as a crypto algorithm (signature, JWS algorithm, public key name, hash, OID). */
    public Optional<CryptoAlgorithm> algorithm(CanonicalKind kind, String raw) {
        return dictionary.lookup(kind, raw).map(entry -> algorithm(raw, entry));
    }

    public Optional<CanonicalEntry> entry(CanonicalKind kind, String raw) {
        return dictionary.lookup(kind, raw);
    }

    public Optional<Integer> keySize(String raw) {
        return dictionary.lookup(CanonicalKind.KEY_SIZE, raw).flatMap(CanonicalEntry::keySizeBits);
    }

    private static boolean isBlockCipher(AlgorithmFamily family) {
        return family == AlgorithmFamily.AES || family == AlgorithmFamily.DES || family == AlgorithmFamily.TRIPLE_DES;
    }

    private static CryptoAlgorithm algorithm(String raw, CanonicalEntry entry) {
        return new CryptoAlgorithm(entry.family().orElse(AlgorithmFamily.UNKNOWN), shown(raw, entry.raw()), entry.mode(), entry.padding(),
                entry.hash(), entry.keySizeBits());
    }

    /**
     * The name as written in the code (D-174), or the dictionary's own spelling when what was written could not be shown:
     * the lookup ignores case, white space and separators, so {@code "DES\t"} finds the DES row but is not a printable name.
     */
    private static String shown(String raw, String canonical) {
        boolean printable = !raw.isEmpty() && raw.length() <= MAX_RAW && !Text.hasControl(raw);
        return printable ? raw : canonical;
    }
}
