import { createContext, useContext } from "react";

export interface WikiNavigationContextType {
  currentPath: string | null;
  navigateTo: (path: string) => void;
  linked: boolean;
}

export const WikiNavigationContext = createContext<WikiNavigationContextType>({
  currentPath: null,
  navigateTo: () => {},
  linked: true,
});

export function useWikiNavigation() {
  return useContext(WikiNavigationContext);
}
