# SoilSignal Final Demo UI Brief

## Goal

The website is not the presentation. It is the product on the second screen.

For tomorrow, the website should make one idea obvious in under 10 seconds:

> SoilSignal estimates final maize yield before harvest, then shows when that estimate becomes useful.

The main user is a farmer or farm manager. Keep the main view sparse. Put the research detail in Methodology and Data.

## Final product questions

1. How early can satellite imagery reliably predict final maize yield?
2. When is the crop likely to reach physiological maturity and its harvest window?
3. Does UAV imagery improve the forecast enough to justify paying for another flight?

Do not add new product questions tonight.

## Main dashboard

Above the fold:

- Location
- Season
- Plot
- Hybrid
- Final yield forecast in bu/ac
- Prediction range
- Forecast date / days after planting
- Simple forecast-through-season chart

Do not show the old custom confidence percentage. It is a display heuristic, not a probability.

Do not call R² "accuracy" or "confidence".

When the final model metrics arrive, farmer-facing copy should prefer MAE or "typical error" over R².

Example:

- Final yield forecast: 184 bu/ac
- Typical validation error: 11.8 bu/ac
- As of: 82 days after planting

R² belongs as supporting evidence in Methodology.

## Explaining R²

If the final validated value remains R² = 0.851, use:

> By about day 82, the model explained roughly 85% of the observed differences in final yield across the validation data.

Shorter farmer-facing version:

> By about day 82, the model captured most of the yield differences we observed between plots.

Never say:

- 85.1% accurate
- 85.1% confidence
- 90% accurate because R² is 0.851

Pair R² with MAE as soon as the ML team provides it.

## U.S. trial map

Overview should include a presentation-friendly vector map.

Visual direction:

- contiguous U.S. outline in muted gray
- no third-party map SDK
- trial locations as green markers
- Ames, IA
- Crawfordsville, IA
- Missouri Valley, IA
- Lincoln, NE
- Scottsbluff, NE
- clicking a marker updates a compact location card
- later, wire the selected site to the frozen final-results JSON
- prefer supplied trial/satellite imagery over Google Maps screenshots

Do not hardcode final model metrics into the map.

## Yield-through-season result

Once ML freezes results, the most important chart is:

x-axis: days after planting
y-axis: validation performance

Prefer to show both:

- MAE, bu/ac
- R², secondary

Highlight the earliest useful stage based on the final frozen results, not a hardcoded "82 days" if that number changes.

## Maturity / GDD

Show:

- accumulated GDD
- estimated current crop stage
- estimated physiological maturity window

Do not promise an exact harvest date unless the method genuinely supports one.

Use "estimated maturity window" or "likely harvest window."

## Satellite vs UAV

Show two side-by-side panels only after the ML team supplies a matched comparison.

Satellite only:
- MAE
- R²

Satellite + UAV:
- MAE
- R²

Then show the delta.

Do not invent:
- narrower intervals
- higher confidence
- dollar ROI

If cost is shown, label it as a user-entered or demo assumption.

## What moves off the main dashboard

Keep implemented, but place in Methodology/Data or behind a detail affordance:

- scouting queue
- raw feature importance
- model-driver details
- NOAA / USDA source diagnostics
- soil details
- historical county yield table
- model reliability tables
- data provenance

## Methodology page

This is where the technical depth should live:

- TIFF six-band processing
- zero-padding mask
- vegetation indices / feature extraction
- Random Forest and model selection
- grouped validation
- R² and MAE versus days after planting
- satellite versus UAV ablation
- GDD method
- data sources and limitations

## Copy style

Use:

- Yield forecast
- Prediction range
- Days after planting
- Expected error
- Satellite imagery
- UAV imagery
- Estimated maturity
- Validation result
- Why this estimate changed

Avoid:

- AI-powered
- progressive intelligence
- signal convergence
- evidence accumulation
- contextual intelligence
- high-confidence signal
- "90% confidence" unless it is a calibrated statistical statement

## Data integration tonight

Do not retrain models from the browser.

The ML team should export one frozen, versioned results artifact. The frontend should consume that artifact through a service/API contract.

Suggested contents:

- model name
- validation split
- metrics by days-after-planting stage
- earliest useful DAP
- per-site/per-plot forecast outputs
- GDD / maturity outputs
- satellite-only metrics
- satellite + UAV metrics

Keep the React components independent of the file format by reading through a service module.

## Demo rule

The main screen should answer "what will my field yield?" before it explains how SoilSignal works.

If a visual element does not help answer yield, maturity timing, or UAV value, it belongs lower on the page or in Methodology.
