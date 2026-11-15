import { Shell } from "@/app/Shell";
import { useSimulation } from "@/hooks/useSimulation";

export default function App() {
  const sim = useSimulation();
  return <Shell sim={sim} />;
}
