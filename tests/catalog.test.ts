import { describe, expect, it, vi } from "vitest";
import catalogJson from "../data/catalog.json";
import { createCatalogStore } from "../src/catalog";
import type { Catalog } from "../src/types";

const catalog = catalogJson as unknown as Catalog;

describe("catalog store", () => {
  it("notifies subscribers and refreshes pattern labels when a catalog is replaced", () => {
    const store = createCatalogStore(catalog);
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    const firstPattern = catalog.patterns[0];
    const updated = {
      ...catalog,
      patterns: catalog.patterns.map((pattern) => pattern.id === firstPattern.id
        ? { ...pattern, label: "Live label" }
        : pattern),
    };

    store.replace(updated);

    expect(store.getSnapshot()).toBe(updated);
    expect(store.patternLabel(firstPattern.id)).toBe("Live label");
    expect(listener).toHaveBeenCalledOnce();

    unsubscribe();
    store.replace(catalog);
    expect(listener).toHaveBeenCalledOnce();
  });
});
