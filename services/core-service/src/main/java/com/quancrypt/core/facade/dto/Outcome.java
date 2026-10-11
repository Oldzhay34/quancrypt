package com.quancrypt.core.facade.dto;

/** A result and whether the resource was created (201) or already existed or was updated (200). */
public record Outcome<T>(boolean created, T body) {
}
