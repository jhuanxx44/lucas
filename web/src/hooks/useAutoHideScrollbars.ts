import { useEffect } from "react";

const SCROLLBAR_HIDE_DELAY_MS = 700;

export function useAutoHideScrollbars() {
  useEffect(() => {
    const hideTimers = new Map<Element, ReturnType<typeof setTimeout>>();

    const handleScroll = (event: Event) => {
      const scrollContainer = event.target instanceof Element
        ? event.target
        : document.scrollingElement;

      if (!scrollContainer) return;

      scrollContainer.classList.add("is-scrolling");
      const currentTimer = hideTimers.get(scrollContainer);
      if (currentTimer) clearTimeout(currentTimer);

      hideTimers.set(scrollContainer, setTimeout(() => {
        scrollContainer.classList.remove("is-scrolling");
        hideTimers.delete(scrollContainer);
      }, SCROLLBAR_HIDE_DELAY_MS));
    };

    document.addEventListener("scroll", handleScroll, true);

    return () => {
      document.removeEventListener("scroll", handleScroll, true);
      hideTimers.forEach((timer, element) => {
        clearTimeout(timer);
        element.classList.remove("is-scrolling");
      });
    };
  }, []);
}
