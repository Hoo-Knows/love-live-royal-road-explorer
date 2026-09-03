import { useSyncExternalStore } from "react";
import catalogJson from "../data/catalog.json";
import type { Catalog, CatalogPattern } from "./types";

type CatalogListener = () => void;

export interface CatalogStore {
  getSnapshot: () => Catalog;
  subscribe: (listener: CatalogListener) => () => void;
  replace: (nextCatalog: Catalog) => void;
  patternLabel: (patternId: string) => string;
}

export function createCatalogStore(initialCatalog: Catalog): CatalogStore {
  let currentCatalog = initialCatalog;
  let patternById = buildPatternLookup(initialCatalog);
  const listeners = new Set<CatalogListener>();

  return {
    getSnapshot: () => currentCatalog,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    replace: (nextCatalog) => {
      currentCatalog = nextCatalog;
      patternById = buildPatternLookup(nextCatalog);
      listeners.forEach((listener) => {
        listener();
      });
    },
    patternLabel: (patternId) => patternById.get(patternId)?.label ?? patternId,
  };
}

function buildPatternLookup(catalog: Catalog): Map<string, CatalogPattern> {
  return new Map(catalog.patterns.map((pattern) => [pattern.id, pattern]));
}

export const catalogStore = createCatalogStore(catalogJson as unknown as Catalog);

export function useCatalog(): Catalog {
  return useSyncExternalStore(
    catalogStore.subscribe,
    catalogStore.getSnapshot,
    catalogStore.getSnapshot,
  );
}

export function patternLabel(patternId: string): string {
  return catalogStore.patternLabel(patternId);
}

if (import.meta.hot) {
  import.meta.hot.accept("../data/catalog.json", (updatedModule) => {
    const updatedCatalog = updatedModule?.default;
    if (updatedCatalog) {
      catalogStore.replace(updatedCatalog as unknown as Catalog);
    }
  });
}
