import type { Graph } from "../lib/types";

const TONES: Record<string, string> = {
  trigger: "#F2A33C",
  action: "#2ED3B7",
  logic: "#A78BFA",
  ai: "#F2795B",
};

function toneFor(type: string): string {
  const prefix = type.split("_")[0];
  return TONES[prefix] ?? "#8B8798";
}

export function GraphPreview({ graph, height = 74 }: { graph: Graph; height?: number }) {
  const nodes = graph.nodes ?? [];
  const edges = graph.edges ?? [];

  if (nodes.length === 0) {
    return (
      <div className="graph-preview graph-preview--empty" style={{ height }}>
        <span>Sem nós</span>
      </div>
    );
  }

  const xs = nodes.map((node) => node.position?.x ?? 0);
  const ys = nodes.map((node) => node.position?.y ?? 0);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const width = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const pad = 14;

  const points = new Map<string, { x: number; y: number }>();
  nodes.forEach((node, index) => {
    const x =
      nodes.length === 1
        ? 60
        : pad + (((node.position?.x ?? index * 120) - minX) / width) * (120 - pad * 2);
    const y =
      maxY === minY
        ? height / 2
        : pad + (((node.position?.y ?? 0) - minY) / spanY) * (height - pad * 2);
    points.set(node.id, { x, y });
  });

  return (
    <svg
      className="graph-preview"
      viewBox={`0 0 120 ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`Prévia do fluxo com ${nodes.length} nós`}
    >
      {edges.map((edge) => {
        const from = points.get(edge.source);
        const to = points.get(edge.target);
        if (!from || !to) return null;
        const mid = (from.x + to.x) / 2;
        return (
          <path
            key={edge.id}
            d={`M ${from.x} ${from.y} C ${mid} ${from.y}, ${mid} ${to.y}, ${to.x} ${to.y}`}
            className="graph-preview__edge"
          />
        );
      })}
      {nodes.map((node) => {
        const point = points.get(node.id);
        if (!point) return null;
        return (
          <circle
            key={node.id}
            cx={point.x}
            cy={point.y}
            r={node.type.startsWith("trigger") ? 3.4 : 2.6}
            fill={toneFor(node.type)}
            className={node.disabled ? "graph-preview__node is-disabled" : "graph-preview__node"}
          />
        );
      })}
    </svg>
  );
}
