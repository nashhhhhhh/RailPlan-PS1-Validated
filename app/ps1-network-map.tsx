"use client";

type LineCode = "ALP" | "BET";
type Bound = "EB" | "WB";

type Props = {
  focusLine: "ALL" | LineCode;
  focusBound: "ALL" | Bound;
  onSelectLine: (line: LineCode) => void;
};

const alphaStations = ["S01", "S02", "S03", "S04", "H01", "H02", "S05", "S06", "S07", "S08"];
const betaStations = ["S11", "S12", "S13", "S14", "H01", "H02", "S15", "S16", "S17", "S18"];
const stationX = [220, 305, 390, 475, 575, 685, 785, 870, 955, 1040];

function NetworkLine({
  code,
  name,
  stations,
  y,
  dimmed,
  focusBound,
  onSelect,
}: {
  code: LineCode;
  name: string;
  stations: string[];
  y: number;
  dimmed: boolean;
  focusBound: "ALL" | Bound;
  onSelect: () => void;
}) {
  const className = code === "ALP" ? "alpha" : "beta";
  const trackColor = code === "ALP" ? "#7adcf4" : "#bd91f2";
  const marker = code === "ALP" ? "url(#alphaArrow)" : "url(#betaArrow)";
  return <g
    className={`psd-svg-line ${className} ${dimmed ? "dimmed" : ""}`}
    onClick={onSelect}
    role="button"
    tabIndex={0}
    aria-label={`Filter dashboard to ${name}`}
    onKeyDown={event => { if (event.key === "Enter" || event.key === " ") onSelect(); }}
  >
    <g className="psd-line-label">
      <rect x="40" y={y - 35} width="130" height="70" rx="12" className="psd-line-label-panel"/>
      <rect x="40" y={y - 35} width="5" height="70" rx="3" className="psd-line-accent"/>
      <text x="60" y={y - 7} className="psd-line-code">{code}</text>
      <text x="60" y={y + 14} className="psd-line-name">{name}</text>
      <text x="151" y={y - 9} textAnchor="end" className="psd-line-bound">EB</text>
      <text x="151" y={y + 17} textAnchor="end" className="psd-line-bound">WB</text>
    </g>

    <line x1="188" y1={y - 10} x2="1092" y2={y - 10} className="psd-track-bed"/>
    <line x1="1092" y1={y + 10} x2="188" y2={y + 10} className="psd-track-bed"/>
    <line x1="188" y1={y - 10} x2="1082" y2={y - 10} stroke={trackColor} className={`psd-track psd-track-eb ${focusBound === "WB" ? "bound-dimmed" : ""}`} markerEnd={marker}/>
    <line x1="1082" y1={y + 10} x2="198" y2={y + 10} stroke={trackColor} className={`psd-track psd-track-wb ${focusBound === "EB" ? "bound-dimmed" : ""}`} markerEnd={marker}/>
    <line x1="188" y1={y - 10} x2="1074" y2={y - 10} stroke={trackColor} className={`psd-energy psd-energy-eb ${focusBound === "WB" ? "bound-dimmed" : ""}`}/>
    <line x1="1082" y1={y + 10} x2="206" y2={y + 10} stroke={trackColor} className={`psd-energy psd-energy-wb ${focusBound === "EB" ? "bound-dimmed" : ""}`}/>

    <circle r="4" fill={code === "ALP" ? "#79dfff" : "#cb8cff"} className={`psd-packet ${focusBound === "WB" ? "bound-dimmed" : ""}`}>
      <animateMotion dur={code === "ALP" ? "7s" : "7.8s"} repeatCount="indefinite" path={`M 205 ${y - 10} L 1068 ${y - 10}`}/>
    </circle>
    <circle r="4" fill={code === "ALP" ? "#8ba8ff" : "#ee8dd0"} className={`psd-packet ${focusBound === "EB" ? "bound-dimmed" : ""}`}>
      <animateMotion dur={code === "ALP" ? "8.2s" : "7.2s"} repeatCount="indefinite" path={`M 1068 ${y + 10} L 212 ${y + 10}`}/>
    </circle>

    {stations.map((station, index) => {
      const x = stationX[index];
      const isHub = station.startsWith("H");
      const labelY = code === "ALP" ? y - 34 : y + 46;
      return <g key={station} className={`psd-station ${isHub ? "psd-hub" : ""}`} transform={`translate(${x} ${y})`}>
        <title>{`${name} ${station}`}</title>
        <line x1="0" y1="-10" x2="0" y2="10" className="psd-station-bridge"/>
        {isHub
          ? <><rect x="-14" y="-20" width="28" height="40" rx="8" className="psd-hub-node"/><circle r="4" className="psd-hub-core"/></>
          : <><circle r="11" className="psd-station-outer"/><circle r="4" className="psd-station-inner"/></>}
        <text x="0" y={labelY - y} textAnchor="middle" className={`psd-station-label ${isHub ? "hub-label" : ""}`}>{station}</text>
      </g>;
    })}
  </g>;
}

export default function PS1NetworkMap({ focusLine, focusBound, onSelectLine }: Props) {
  return <div className="psd-smart-network">
    <div className="psd-map-hint">Select a line to filter the dashboard</div>
    <svg viewBox="0 0 1180 430" role="img" aria-labelledby="psd-network-title psd-network-description">
      <title id="psd-network-title">Line Alpha and Line Beta network topology</title>
      <desc id="psd-network-description">Two independent directional metro lines with separate H01 and H02 capacity. Live work can create cross-line closure.</desc>
      <defs>
        <pattern id="microGrid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M 28 0 L 0 0 0 28" fill="none" stroke="#263656" strokeWidth=".6" opacity=".22"/></pattern>
        <marker id="alphaArrow" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="11" markerHeight="11" markerUnits="userSpaceOnUse" orient="auto"><path d="M 1 1 L 11 6 L 1 11 Z" fill="#7adcf4"/></marker>
        <marker id="betaArrow" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="11" markerHeight="11" markerUnits="userSpaceOnUse" orient="auto"><path d="M 1 1 L 11 6 L 1 11 Z" fill="#bd91f2"/></marker>
      </defs>
      <rect width="1180" height="430" fill="url(#microGrid)"/>
      <text x="40" y="40" className="psd-map-title">DUAL-LINE NETWORK TOPOLOGY</text>
      <text x="40" y="64" className="psd-map-subtitle">Directional track capacity with line-specific interchange sectors</text>
      <g className="psd-map-legend" transform="translate(790 25)">
        <rect width="345" height="54" rx="10"/>
        <path d="M 18 18 L 74 18" className="legend-eb-line"/><text x="84" y="22">EB · Eastbound</text>
        <path d="M 185 18 L 241 18" className="legend-wb-line"/><text x="251" y="22">WB · Westbound</text>
        <text x="18" y="42" className="legend-detail">Moving dots show direction only</text>
      </g>

      <g className="psd-interchange-zone">
        <rect x="532" y="92" width="196" height="280" rx="18"/>
        <text x="630" y="113" textAnchor="middle">H01–H02 INTERCHANGE</text>
      </g>
      <path d="M 575 177 L 575 305" className="psd-crossline-link"/>
      <path d="M 685 177 L 685 305" className="psd-crossline-link"/>

      <NetworkLine code="ALP" name="Line Alpha" stations={alphaStations} y={165} dimmed={focusLine === "BET"} focusBound={focusBound} onSelect={() => onSelectLine("ALP")}/>
      <NetworkLine code="BET" name="Line Beta" stations={betaStations} y={315} dimmed={focusLine === "ALP"} focusBound={focusBound} onSelect={() => onSelectLine("BET")}/>

      <g className="psd-crossover">
        <rect x="548" y="222" width="164" height="52" rx="10"/>
        <text x="630" y="243" textAnchor="middle">LIVE WORK ONLY</text>
        <text x="630" y="260" textAnchor="middle" className="psd-crossover-detail">may close both lines</text>
      </g>
    </svg>
  </div>;
}
