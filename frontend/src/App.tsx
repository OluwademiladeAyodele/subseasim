import { Dashboard } from "@/dashboard/Dashboard";
import { useSimulation } from "@/hooks/useSimulation";

export default function App() {
  const sim = useSimulation();
  return <Dashboard sim={sim} />;
}
