import { motion, useReducedMotion } from 'motion/react';
import { ArrowRight } from 'lucide-react';
import { APP_CONFIG } from '../../config/appConfig';
import { EASE_OUT } from '../../utils/motion';
import { Link } from '../../utils/router';
import { Reveal } from '../common/Reveal';
import { HeroSystemAnimation } from './HeroSystemAnimation';
import { ForecastPreview } from './ForecastPreview';
import { Principles } from './Principles';

export function OverviewPage() {
  const reduce = useReducedMotion();
  const rise = (delay: number) => ({
    initial: reduce ? (false as const) : { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.7, ease: EASE_OUT, delay },
  });

  return (
    <>
      <section className="relative overflow-x-clip" aria-labelledby="hero-heading">
        <div className="mx-auto max-w-6xl px-4 pt-12 sm:px-6 sm:pt-16 lg:pt-20">
          <motion.h1
            id="hero-heading"
            className="max-w-[16ch] text-[42px] leading-[1.02] font-semibold tracking-[-0.04em] text-balance text-ink sm:text-[58px] lg:max-w-none lg:text-[66px]"
            {...rise(0.05)}
          >
            {APP_CONFIG.tagline}
          </motion.h1>
          <motion.p
            className="mt-5 max-w-[34rem] text-[17px] leading-relaxed text-pretty text-muted sm:text-[19px]"
            {...rise(0.15)}
          >
            SoilSignal turns crop observations and environmental context into progressive, interpretable yield
            forecasts.
          </motion.p>
          <motion.div className="mt-8 flex flex-wrap items-center gap-3" {...rise(0.25)}>
            <Link
              to="dashboard"
              className="lift group inline-flex items-center gap-2 rounded-full bg-leaf-700 px-5 py-2.5 text-[15px] font-medium text-white shadow-[0_1px_2px_rgb(8_108_76/0.25)] hover:bg-leaf-800 hover:shadow-lift"
            >
              Explore Forecast
              <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
            </Link>
            <Link
              to="methodology"
              className="lift inline-flex items-center rounded-full border border-line-strong bg-surface px-5 py-2.5 text-[15px] font-medium text-ink hover:border-faint hover:shadow-float"
            >
              How It Works
            </Link>
          </motion.div>
        </div>
        <div className="mx-auto mt-8 max-w-6xl px-3 sm:mt-6 sm:px-6">
          <HeroSystemAnimation />
        </div>
      </section>

      <ForecastPreview />

      <Principles />

      <section className="mx-auto max-w-6xl px-4 pb-24 sm:px-6">
        <Reveal className="flex flex-col gap-6 rounded-2xl border border-line bg-surface px-6 py-8 sm:px-10 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-[22px] font-semibold tracking-[-0.02em] text-ink sm:text-[26px]">Move through a growing season.</h2>
            <p className="mt-2 max-w-lg text-[15px] leading-relaxed text-muted">
              Scrub from emergence to maturity and watch the forecast, its range and its drivers update together.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              to="dashboard"
              className="lift inline-flex items-center gap-2 rounded-full bg-leaf-700 px-5 py-2.5 text-[15px] font-medium text-white hover:bg-leaf-800 hover:shadow-lift"
            >
              Explore Forecast
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              to="about"
              className="lift inline-flex items-center rounded-full border border-line-strong px-5 py-2.5 text-[15px] font-medium text-ink hover:border-faint"
            >
              Meet the team
            </Link>
          </div>
        </Reveal>
      </section>
    </>
  );
}
