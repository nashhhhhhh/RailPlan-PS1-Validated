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
  const gradient = code === "ALP" ? "url(#alphaGradient)" : "url(#betaGradient)";
  const marker = code === "ALP" ? "url(#alphaArrow)" : "url(#betaArrow)";
  return <g className={`psd-svg-line ${className} ${dimmed ? "dimmed" : ""}`} onClick={onSelect} role="button" tabIndex={0} aria-label={`Focus ${name}`} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") onSelect(); }}>
    <g className="psd-line-label">
      <rect x="42" y={y - 30} width="124" height="62" rx="15" fill={`url(#${className}Panel)`}/>
      <rect x="43" y={y - 29} width="122" height="60" rx="14" className="psd-line-label-border"/>
      <text x="62" y={y - 5} className="psd-line-code">{code}</text>
      <text x="62" y={y + 15} className="psd-line-name">{name}</text>
      <circle cx="143" cy={y} r="7" className="psd-line-live"/>
    </g>

    <path d={`M 205 ${y + 17} L 1090 ${y + 17}`} className="psd-track-depth"/>
    <path d={`M 205 ${y - 12} L 1090 ${y - 12}`} className="psd-track-depth"/>
    <path d={`M 205 ${y - 17} L 1090 ${y - 17}`} stroke={gradient} className={`psd-track psd-track-eb ${focusBound === "WB" ? "bound-dimmed" : ""}`} markerEnd={marker}/>
    <path d={`M 1090 ${y + 12} L 205 ${y + 12}`} stroke={gradient} className={`psd-track psd-track-wb ${focusBound === "EB" ? "bound-dimmed" : ""}`} markerEnd={marker}/>
    <path d={`M 205 ${y - 17} L 1090 ${y - 17}`} stroke={gradient} className={`psd-energy psd-energy-eb ${focusBound === "WB" ? "bound-dimmed" : ""}`}/>
    <path d={`M 1090 ${y + 12} L 205 ${y + 12}`} stroke={gradient} className={`psd-energy psd-energy-wb ${focusBound === "EB" ? "bound-dimmed" : ""}`}/>
    <text x="1112" y={y - 12} className="psd-bound-label">EB</text>
    <text x="184" y={y + 17} className="psd-bound-label" textAnchor="end">WB</text>

    <circle r="5" fill={code === "ALP" ? "#73e8ff" : "#dc8cff"} className={`psd-packet ${focusBound === "WB" ? "bound-dimmed" : ""}`}>
      <animateMotion dur={code === "ALP" ? "5.6s" : "6.4s"} repeatCount="indefinite" path={`M 205 ${y - 17} L 1080 ${y - 17}`}/>
    </circle>
    <circle r="4" fill={code === "ALP" ? "#8ba8ff" : "#9b8cff"} className={`psd-packet ${focusBound === "EB" ? "bound-dimmed" : ""}`}>
      <animateMotion dur={code === "ALP" ? "7.1s" : "5.8s"} repeatCount="indefinite" path={`M 1080 ${y + 12} L 205 ${y + 12}`}/>
    </circle>

    {stations.map((station, index) => {
      const x = stationX[index];
      const isHub = station.startsWith("H");
      if (isHub) return <g key={station} className="psd-hub" transform={`translate(${x} ${y - 2})`}>
        <path d="M -17 -24 L 11 -24 L 18 -17 L -10 -17 Z" className="psd-hub-top"/>
        <path d="M 11 -24 L 18 -17 L 18 20 L 11 27 Z" className="psd-hub-side"/>
        <rect x="-17" y="-17" width="28" height="44" rx="7" className="psd-hub-face"/>
        <rect x="-11" y="-11" width="16" height="32" rx="4" className="psd-hub-core"/>
        <text x="0" y="-34" textAnchor="middle" className="psd-station-label hub-label">{station}</text>
      </g>;
      return <g key={station} className="psd-station" transform={`translate(${x} ${y - 2})`}>
        <ellipse cx="0" cy="8" rx="13" ry="6" className="psd-station-shadow"/>
        <circle r="13" className="psd-station-outer"/>
        <circle r="7" className="psd-station-inner"/>
        <text x="0" y={index % 2 === 0 ? -28 : 36} textAnchor="middle" className="psd-station-label">{station}</text>
      </g>;
    })}
  </g>;
}

export default function PS1NetworkMap({ focusLine, focusBound, onSelectLine }: Props) {
  return <div className="psd-smart-network">
    <div className="psd-network-orbit orbit-one"/>
    <div className="psd-network-orbit orbit-two"/>
    <svg viewBox="0 0 1180 430" role="img" aria-labelledby="psd-network-title psd-network-description">
      <title id="psd-network-title">Animated Line Alpha and Line Beta topology</title>
      <desc id="psd-network-description">Two independent directional metro lines with interchange stations H01 and H02. Only Live work crosses between lines.</desc>
      <defs>
        <linearGradient id="alphaGradient" x1="0" x2="1"><stop offset="0" stopColor="#65e9ff"/><stop offset=".52" stopColor="#5db6ff"/><stop offset="1" stopColor="#8a8cff"/></linearGradient>
        <linearGradient id="betaGradient" x1="0" x2="1"><stop offset="0" stopColor="#9d8cff"/><stop offset=".52" stopColor="#c479ff"/><stop offset="1" stopColor="#ef78cf"/></linearGradient>
        <linearGradient id="alphaPanel" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#163c5d"/><stop offset="1" stopColor="#1b2450"/></linearGradient>
        <linearGradient id="betaPanel" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#31265c"/><stop offset="1" stopColor="#4a2453"/></linearGradient>
        <linearGradient id="hubGradient" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#f2d06b"/><stop offset="1" stopColor="#bd7d37"/></linearGradient>
        <pattern id="microGrid" width="25" height="25" patternUnits="userSpaceOnUse"><path d="M 25 0 L 0 0 0 25" fill="none" stroke="#263656" strokeWidth=".7" opacity=".35"/></pattern>
        <filter id="alphaGlow" x="-30%" y="-100%" width="160%" height="300%"><feGaussianBlur stdDeviation="5" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <filter id="betaGlow" x="-30%" y="-100%" width="160%" height="300%"><feGaussianBlur stdDeviation="5" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <marker id="alphaArrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8a8cff"/></marker>
        <marker id="betaArrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#ef78cf"/></marker>
      </defs>
      <rect width="1180" height="430" fill="url(#microGrid)"/>
      <text x="42" y="42" className="psd-map-title">LIVE NETWORK DIGITAL TWIN</text>
      <text x="42" y="65" className="psd-map-subtitle">Directional capacity · animated access flow · H01↔H02 dual-line interchange</text>
      <g className="psd-map-legend" transform="translate(815 28)">
        <rect width="322" height="48" rx="12"/>
        <circle cx="20" cy="17" r="4" className="legend-eb"/><text x="32" y="20">EB · Eastbound</text>
        <circle cx="166" cy="17" r="4" className="legend-wb"/><text x="178" y="20">WB · Westbound</text>
        <text x="20" y="37" className="legend-detail">Pulses indicate direction, not live train positions</text>
      </g>

      <NetworkLine code="ALP" name="Line Alpha" stations={alphaStations} y={155} dimmed={focusLine === "BET"} focusBound={focusBound} onSelect={() => onSelectLine("ALP")}/>
      <NetworkLine code="BET" name="Line Beta" stations={betaStations} y={325} dimmed={focusLine === "ALP"} focusBound={focusBound} onSelect={() => onSelectLine("BET")}/>

      <g className="psd-crossover">
        <path d="M 575 187 C 575 225 575 255 575 293"/>
        <path d="M 685 187 C 685 225 685 255 685 293"/>
        <circle cx="575" cy="240" r="4"/><circle cx="685" cy="240" r="4"/>
        <rect x="590" y="216" width="80" height="47" rx="10"/>
        <text x="630" y="235" textAnchor="middle">LIVE ONLY</text>
        <text x="630" y="251" textAnchor="middle" className="psd-crossover-detail">cross-line closure</text>
      </g>
    </svg>
    <div className="psd-network-depth"/>
    <div className="psd-live-readout"><i/><span>Topology model online</span><b>20</b><small>station records</small></div>
  </div>;
}
