import React, { useState, useEffect } from 'react';
import { FieldMeta, FieldForecast } from '../../types/agricultural';
import { ALL_FIELDS, PURDUE_104_DATA } from '../../mock/fieldsData';
import { getForecast } from '../../services/forecasts';
import { FieldContextBar } from './FieldContextBar';
import { ForecastOverview } from './ForecastOverview';
import { ForecastTimeline } from './ForecastTimeline';
import { CropDevelopment } from './CropDevelopment';
import { EnvironmentalContext } from './EnvironmentalContext';
import { SpatialFieldView } from './SpatialFieldView';
import { ModelExplanation } from './ModelExplanation';
import { HistoricalComparison } from './HistoricalComparison';
import { DataSources } from './DataSources';
import { DemoControlRibbon } from './DemoControlRibbon';
import { ModuleSkeleton, ErrorCard, EmptyModuleState } from '../common/SkeletonLoader';

interface DashboardViewProps {
  isPresentationMode: boolean;
  onTogglePresentationMode: () => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  isPresentationMode,
  onTogglePresentationMode,
}) => {
  // Current active field (defaults to Purdue 104)
  const [selectedField, setSelectedField] = useState<FieldMeta>(PURDUE_104_DATA.field);
  const [fieldData, setFieldData] = useState<FieldForecast>(PURDUE_104_DATA);

  // Active snapshot index along growing season (defaults to index 4: July 22)
  const [activeSnapshotIndex, setActiveSnapshotIndex] = useState<number>(4);

  // Simulation states for hackathon judging & testing (items 24, 25)
  const [simulateLoading, setSimulateLoading] = useState<boolean>(false);
  const [simulateMissingSatellite, setSimulateMissingSatellite] = useState<boolean>(false);
  const [simulateWeatherError, setSimulateWeatherError] = useState<boolean>(false);

  // Load field forecast when selected field changes
  useEffect(() => {
    let isMounted = true;
    getForecast(selectedField.id).then((data) => {
      if (isMounted) {
        setFieldData(data);
        // Keep active index within bounds
        setActiveSnapshotIndex((prev) => Math.min(prev, data.snapshots.length - 1));
      }
    });
    return () => {
      isMounted = false;
    };
  }, [selectedField.id]);

  // Reset to default Purdue 104 July 22 snapshot
  const handleResetDemo = () => {
    setSelectedField(PURDUE_104_DATA.field);
    setFieldData(PURDUE_104_DATA);
    setActiveSnapshotIndex(4); // July 22
    setSimulateLoading(false);
    setSimulateMissingSatellite(false);
    setSimulateWeatherError(false);
  };

  // Keyboard shortcut listener (Item 26)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if user is typing in an input
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName)) {
        return;
      }

      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        setActiveSnapshotIndex((prev) => Math.max(0, prev - 1));
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        setActiveSnapshotIndex((prev) =>
          Math.min(fieldData.snapshots.length - 1, prev + 1)
        );
      } else if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        handleResetDemo();
      } else if (e.key === 'p' || e.key === 'P' || e.key === 'f' || e.key === 'F') {
        e.preventDefault();
        onTogglePresentationMode();
      } else if (['1', '2', '3', '4', '5'].includes(e.key)) {
        const num = parseInt(e.key, 10) - 1;
        if (ALL_FIELDS[num]) {
          setSelectedField(ALL_FIELDS[num].field);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [fieldData.snapshots.length, onTogglePresentationMode]);

  const activeSnapshot = fieldData.snapshots[activeSnapshotIndex] || fieldData.snapshots[0];

  return (
    <div className="flex flex-col min-h-screen bg-[#FBFBFA]">
      {/* 1. Field Context Bar */}
      <FieldContextBar
        fields={ALL_FIELDS.map((f) => f.field)}
        selectedField={selectedField}
        onSelectField={(f) => setSelectedField(f)}
        activeDateDisplay={activeSnapshot.displayDate}
        stageName={activeSnapshot.stage}
        isPresentationMode={isPresentationMode}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-5 space-y-5">
        {/* Loading Shimmer Simulation */}
        {simulateLoading ? (
          <div className="space-y-5 animate-in fade-in duration-200">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <ModuleSkeleton height="h-36" />
              <ModuleSkeleton height="h-36" />
              <ModuleSkeleton height="h-36" />
            </div>
            <ModuleSkeleton height="h-96" />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <ModuleSkeleton height="h-80" />
              <ModuleSkeleton height="h-80" />
            </div>
          </div>
        ) : (
          <>
            {/* 2. Primary Forecast Cards (Predicted Yield, Forecast Range, Confidence) */}
            <ForecastOverview
              snapshot={activeSnapshot}
              field={selectedField}
              isPresentationMode={isPresentationMode}
            />

            {/* 3. Main Feature: Growing-Season Forecast Timeline & Interactive Date Slider */}
            <ForecastTimeline
              snapshots={fieldData.snapshots}
              activeSnapshotIndex={activeSnapshotIndex}
              onSelectSnapshotIndex={(idx) => setActiveSnapshotIndex(idx)}
              isPresentationMode={isPresentationMode}
            />

            {/* 4. Side-by-Side: Crop Development Signal & Environmental Context */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-stretch">
              {/* Crop Signal Chart (NDVI / NDRE + Event Markers) */}
              {simulateMissingSatellite ? (
                <EmptyModuleState
                  title="No satellite observations available for this period"
                  subtext="Cloud obstruction or orbital gap on this date. Weather and soil context remain fully synchronized."
                />
              ) : (
                <CropDevelopment
                  timeline={fieldData.fullVegetationSeries || fieldData.vegetationTimeline || []}
                  events={fieldData.events}
                  activeDateDisplay={activeSnapshot.displayDate}
                  activeDateIso={activeSnapshot.date}
                />
              )}

              {/* Environmental Context (Weather / Soil) */}
              {simulateWeatherError ? (
                <ErrorCard
                  title="Environmental Telemetry Gateway Error"
                  message="Failed to fetch latest PRISM grid cell telemetry. Regional historical averages loaded as fallback."
                  onRetry={() => setSimulateWeatherError(false)}
                />
              ) : (
                <EnvironmentalContext
                  weather={activeSnapshot.weather}
                  soil={activeSnapshot.soil}
                />
              )}
            </div>

            {/* 5. Spatial Field View (Polygonal Zones Matrix + Inspector HUD) */}
            <SpatialFieldView
              spatial={fieldData.spatial || activeSnapshot.spatial}
              fieldName={selectedField.name}
            />

            {/* 6. Explainability Section (Why is the model predicting this? + Feature Weights) */}
            <ModelExplanation
              explanations={activeSnapshot.explanations}
              featureImportance={fieldData.featureImportance || activeSnapshot.featureImportance}
            />

            {/* 7. Historical Comparison (USDA NASS County Benchmark) */}
            <HistoricalComparison
              historical={fieldData.historical}
              currentForecastYield={activeSnapshot.yield}
            />

            {/* 8. Data Provenance & Freshness (Transparent source badges) */}
            <DataSources
              sources={fieldData.sources}
              forecastGeneratedAt={
                fieldData.metadata?.forecastGeneratedAt ||
                `${activeSnapshot.displayDate}, 2026 · ${activeSnapshot.generatedAt}`
              }
            />
          </>
        )}
      </main>

      {/* 9. Demo Control Ribbon & Presentation Facilitator */}
      <DemoControlRibbon
        fields={ALL_FIELDS.map((f) => f.field)}
        selectedField={selectedField}
        onSelectField={(f) => setSelectedField(f)}
        isPresentationMode={isPresentationMode}
        onTogglePresentationMode={onTogglePresentationMode}
        onResetDemo={handleResetDemo}
        simulateLoading={simulateLoading}
        onToggleSimulateLoading={() => setSimulateLoading(!simulateLoading)}
        simulateMissingSatellite={simulateMissingSatellite}
        onToggleSimulateMissingSatellite={() =>
          setSimulateMissingSatellite(!simulateMissingSatellite)
        }
        simulateWeatherError={simulateWeatherError}
        onToggleSimulateWeatherError={() =>
          setSimulateWeatherError(!simulateWeatherError)
        }
      />
    </div>
  );
};
