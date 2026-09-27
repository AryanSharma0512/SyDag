import { Fragment } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { ArrowDown, ArrowRight } from 'lucide-react';
import { EASE_OUT } from '../../utils/motion';

interface Step {
  title: string;
  detail: string;
  tone?: 'input' | 'model' | 'output';
}

interface MethodPipelineProps {
  /** The model's name as the results or the deployed models report it. */
  modelLabel: string;
  modelDetail: string;
}

/**
 * The pipeline in plain boxes: imagery becomes plot features, joins the field record
 * and weather, and one model turns them into a final-yield forecast. A static diagram,
 * readable without animation or scrolling.
 */
export function MethodPipeline({ modelLabel, modelDetail }: MethodPipelineProps) {
  const reduce = useReducedMotion();
  const imagery: Step[] = [
    { title: 'Satellite TIFFs', detail: '6 spectral bands per plot image', tone: 'input' },
    { title: 'Mask plot pixels', detail: 'Drop the zero padding and invalid pixels' },
    { title: 'Spectral and vegetation features', detail: 'Band reflectance, NDVI, NDRE, GNDVI, EVI, change between passes' },
  ];
  const joins: Step[] = [
    { title: 'Field records', detail: 'Hybrid, nitrogen, irrigation, planting date', tone: 'input' },
    { title: 'Weather', detail: 'Rain, heat and growing degree days since planting', tone: 'input' },
  ];
  const tail: Step[] = [
    { title: modelLabel, detail: modelDetail, tone: 'model' },
    { title: 'Final yield prediction', detail: 'bu/ac, with a prediction range', tone: 'output' },
  ];

  const box = (step: Step, i: number) => (
    <motion.div
      key={step.title}
      className={`rounded-xl border px-4 py-3 ${
        step.tone === 'output'
          ? 'border-leaf-700 bg-leaf-700 text-white'
          : step.tone === 'model'
            ? 'border-leaf-200 bg-leaf-50'
            : step.tone === 'input'
              ? 'border-line-strong bg-surface'
              : 'border-line bg-surface'
      }`}
      initial={reduce ? false : { opacity: 0, y: 8 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.4, ease: EASE_OUT, delay: i * 0.06 }}
    >
      <div className={`text-[15px] font-semibold tracking-[-0.01em] ${step.tone === 'output' ? 'text-white' : 'text-ink'}`}>
        {step.title}
      </div>
      <div className={`mt-0.5 text-[13px] leading-snug ${step.tone === 'output' ? 'text-white/80' : 'text-muted'}`}>
        {step.detail}
      </div>
    </motion.div>
  );

  const down = <ArrowDown className="mx-auto h-4 w-4 text-faint" aria-hidden="true" />;

  return (
    <figure aria-label="SoilSignal pipeline: satellite images are masked to the plot and turned into features, joined with field records and weather, and a model predicts final yield.">
      <div className="grid grid-cols-1 items-center gap-3 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,0.9fr)_auto_minmax(0,1fr)]">
        <div className="space-y-2">
          {imagery.map((s, i) => (
            <Fragment key={s.title}>
              {i > 0 && down}
              {box(s, i)}
            </Fragment>
          ))}
        </div>
        <ArrowRight className="mx-auto hidden h-5 w-5 text-faint lg:block" aria-hidden="true" />
        <div className="mx-auto lg:hidden">{down}</div>
        <div className="space-y-2">
          <p className="text-center text-[12px] font-medium tracking-[0.06em] text-faint uppercase">joined with</p>
          {joins.map((s, i) => box(s, i + 3))}
          <p className="text-center text-[12px] text-muted">Only data available on the forecast date</p>
        </div>
        <ArrowRight className="mx-auto hidden h-5 w-5 text-faint lg:block" aria-hidden="true" />
        <div className="mx-auto lg:hidden">{down}</div>
        <div className="space-y-2">
          {tail.map((s, i) => (
            <Fragment key={s.title}>
              {i > 0 && down}
              {box(s, i + 5)}
            </Fragment>
          ))}
        </div>
      </div>
    </figure>
  );
}
