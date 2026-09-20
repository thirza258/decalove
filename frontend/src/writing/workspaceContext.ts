import { createContext, useContext } from "react";
import type { WorkspaceContextValue } from "./workspace";

export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function useWritingWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) throw new Error("Writing pages need a workspace provider");
  return context;
}
