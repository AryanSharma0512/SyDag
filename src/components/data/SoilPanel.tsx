import type { ReactNode } from 'react';
import type { ContextPart, SoilProfile } from '../../types/agricultural';
import { formatNumber } from '../../utils/formatters';
import { DataPanel, DataTable, DerivedTag, Lineage, NotReported, type Column, type SourceState } from './DataPanel';

interface Property {
  key: keyof SoilProfile;
  label: string;
  unit?: string;
  /** Calculated by the SoilSignal backend from the survey's horizon data. */
  derived?: boolean;
  format?: (value: number) => string;
}

const GROUPS: Array<{ title: string; properties: Property[] }> = [
  {
    title: 'Map unit',
    properties: [
      { key: 'mapUnitName', label: 'Map unit' },
      { key: 'series', label: 'Dominant series' },
      { key: 'componentPercent', label: 'Dominant component', unit: '% of map unit', format: (v) => formatNumber(v) },
      { key: 'taxonomicClass', label: 'Taxonomic class' },
    ],
  },
  {
    title: 'Surface layer',
    properties: [
      { key: 'texture', label: 'Surface texture' },
      { key: 'organicMatter', label: 'Organic matter', unit: '%', format: (v) => formatNumber(v, 1) },
      { key: 'ph', label: 'pH', format: (v) => formatNumber(v, 1) },
    ],
  },
  {
    title: 'Drainage & landscape',
    properties: [
      { key: 'drainage', label: 'Drainage' },
      { key: 'hydrologicGroup', label: 'Hydrologic group' },
      { key: 'slopePercent', label: 'Slope', unit: '%', format: (v) => formatNumber(v, 1) },
    ],
  },
  {
    title: 'Water & rooting',
    properties: [
      { key: 'availableWaterCapacity', label: 'Available water capacity', unit: 'cm/cm, top 100 cm', derived: true, format: (v) => formatNumber(v, 3) },
      { key: 'availableWaterStorageCm', label: 'Available water storage', unit: 'cm, top 100 cm', derived: true, format: (v) => formatNumber(v, 1) },
      { key: 'availableWaterClass', label: 'Available water class', derived: true },
      { key: 'rootZoneDepthCm', label: 'Root-zone depth', unit: 'cm', derived: true, format: (v) => formatNumber(v) },
    ],
  },
];

const PROPERTIES = GROUPS.flatMap((g) => g.properties);

const OBSERVED = ['Map unit and components', 'Texture', 'Drainage class', 'Hydrologic group', 'Organic matter', 'pH', 'Slope', 'Horizon water capacity'];
const DERIVED = ['Dominant component', 'Available water capacity and storage (top 100 cm)', 'Available water class', 'Root-zone depth'];

/** The value as reported, or null when SSURGO has none. Never substitutes a default. */
function valueOf(profile: SoilProfile, p: Property): string | null {
  const raw = profile[p.key];
  if (raw === null || raw === undefined || raw === '') return null;
  return typeof raw === 'number' && p.format ? p.format(raw) : String(raw);
}

function PropertyValue({ profile, property }: { profile: SoilProfile; property: Property }) {
  const value = valueOf(profile, property);
  if (value === null) return <NotReported />;
  return (
    <>
      <span className={typeof profile[property.key] === 'number' ? 'data' : ''}>{value}</span>
      {property.unit && <span className="ml-1.5 text-[12px] text-muted">{property.unit}</span>}
    </>
  );
}

/**
 * A schematic soil column: depth scale, the top 100 cm that available water is
 * summarized over, and the root-zone depth. Only reported depths are drawn.
 */
function SoilColumn({ profile }: { profile: SoilProfile }) {
  const root = profile.rootZoneDepthCm;
  const maxDepth = Math.max(200, Math.ceil(((root ?? 0) + 25) / 50) * 50);
  const top = 14;
  const h = 250;
  const y = (cm: number) => top + (cm / maxDepth) * h;
  const ticks = Array.from({ length: maxDepth / 50 + 1 }, (_, i) => i * 50);
  return (
    <svg viewBox={`0 0 190 ${top + h + 12}`} className="h-auto w-full max-w-[220px]" role="img" aria-label={`Soil column: root zone ${root ?? 'not reported'} cm deep`}>
      <defs>
        <linearGradient id="soil-depth" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#bc8758" stopOpacity="0.55" />
          <stop offset="0.35" stopColor="#d3a882" stopOpacity="0.45" />
          <stop offset="1" stopColor="#e6ccb4" stopOpacity="0.35" />
        </linearGradient>
      </defs>
      {ticks.map((cm) => (
        <g key={cm}>
          <line x1={34} x2={40} y1={y(cm)} y2={y(cm)} className="stroke-faint" />
          <text x={30} y={y(cm) + 4} textAnchor="end" className="data fill-faint text-[10px]">
            {cm === 0 ? '0 cm' : cm}
          </text>
        </g>
      ))}
      <rect x={44} y={top} width={56} height={h} rx={6} fill="url(#soil-depth)" />
      <line x1={44} x2={100} y1={top} y2={top} className="stroke-soil-600" strokeWidth={2} />

      {/* Top 100 cm: where available water is summarized */}
      <path d={`M108,${y(0) + 1}h5V${y(100)}h-5`} fill="none" className="stroke-rain-500" strokeWidth={1.5} />
      <text x={118} y={y(50) - 2} className="fill-ink-soft text-[11px]">
        Water
      </text>
      <text x={118} y={y(50) + 12} className="data fill-muted text-[10.5px]">
        {profile.availableWaterStorageCm !== null ? `${formatNumber(profile.availableWaterStorageCm, 1)} cm` : 'n/r'}
      </text>

      {root !== null && (
        <g>
          <line x1={40} x2={104} y1={y(root)} y2={y(root)} className="stroke-ink-soft" strokeWidth={1.5} strokeDasharray="4 3" />
          <text x={118} y={y(root) + 4} className="fill-ink-soft text-[11px]">
            Root zone
          </text>
          <text x={118} y={y(root) + 18} className="data fill-muted text-[10.5px]">
            {formatNumber(root)} cm
          </text>
        </g>
      )}
    </svg>
  );
}

const COLUMNS: Column<Property & { profile: SoilProfile }>[] = [
  { key: 'property', label: 'Property', render: (p) => <span className="data text-ink-soft">{p.key}</span> },
  { key: 'label', label: 'Meaning', render: (p) => p.label },
  { key: 'value', label: 'Value', render: (p) => <PropertyValue profile={p.profile} property={p} /> },
  {
    key: 'origin',
    label: 'Origin',
    render: (p) => (p.derived ? <DerivedTag>Derived by SoilSignal</DerivedTag> : <span className="text-muted">Reported by SSURGO</span>),
  },
];

interface SoilPanelProps {
  part: ContextPart<SoilProfile> | null;
  state: SourceState;
  showData: boolean;
}

export function SoilPanel({ part, state, showData }: SoilPanelProps) {
  const profile = part?.data;
  let body: ReactNode = null;
  if (profile) {
    body = showData ? (
      <DataTable
        caption="Soil profile properties"
        columns={COLUMNS}
        rows={PROPERTIES.map((p) => ({ ...p, profile }))}
        rowKey={(p) => p.key}
      />
    ) : (
      <div className="grid gap-10 md:grid-cols-[200px_minmax(0,1fr)] lg:gap-14">
        <div className="hidden md:block">
          <SoilColumn profile={profile} />
        </div>
        <div className="grid gap-x-12 gap-y-8 sm:grid-cols-2">
          {GROUPS.map((group) => (
            <div key={group.title}>
              <h3 className="text-[12px] font-medium tracking-wide text-soil-700 uppercase">{group.title}</h3>
              <dl className="mt-2">
                {group.properties.map((p) => (
                  <div key={p.key} className="flex items-baseline justify-between gap-4 border-b border-line py-2.5 last:border-b-0">
                    <dt className="flex items-center gap-2 text-[13px] text-muted">
                      {p.label}
                      {p.derived && (
                        <span
                          className="h-2 w-2 shrink-0 rounded-full border border-dashed border-faint"
                          title="Derived by SoilSignal"
                          aria-label="Derived by SoilSignal"
                        />
                      )}
                    </dt>
                    <dd className="text-right text-[14px] text-ink">
                      <PropertyValue profile={profile} property={p} />
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <DataPanel
      id="soil"
      source="soil"
      title="Soil profile"
      subtitle="The dominant soil mapped at the field's coordinates in the USDA soil survey."
      state={state}
      message={part?.message ?? null}
      lineage={profile && <Lineage source={profile.source} retrievedAt={profile.retrievedAt} observed={OBSERVED} derived={DERIVED} />}
    >
      {body}
      {profile && !showData && (
        <p className="mt-6 flex items-center gap-2 text-[12px] text-muted">
          <span className="h-2 w-2 rounded-full border border-dashed border-faint" aria-hidden="true" />
          Derived by SoilSignal from the survey's horizon data. Map unit key <span className="data">{profile.mapUnitKey}</span>
        </p>
      )}
    </DataPanel>
  );
}
