package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

/** What a project file is, which decides the detectors that read it. */
public enum FileKind {
    JAVA,
    SPRING_YAML,
    SPRING_PROPERTIES,
    MOSQUITTO_CONF,
    PEM,
    KEYSTORE,
    POM,
    GRADLE,
    COMPOSE,
    KUBERNETES,
    OTHER
}
