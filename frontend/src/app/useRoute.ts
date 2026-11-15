import { useCallback, useEffect, useState } from "react";

import { ROUTE_BY_ID, type RouteId } from "./routes";

function parse(): RouteId {
  const id = window.location.hash.replace(/^#\/?/, "").split(/[/?]/)[0] as RouteId;
  return id && id in ROUTE_BY_ID ? id : "overview";
}

/** Hash routing: deep-linkable workspaces with working back/forward. */
export function useRoute(): [RouteId, (r: RouteId) => void] {
  const [route, setRoute] = useState<RouteId>(parse);
  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = useCallback((r: RouteId) => {
    if (parse() !== r) window.location.hash = `/${r}`;
    else setRoute(r);
  }, []);
  return [route, go];
}
