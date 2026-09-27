import { motion, useReducedMotion } from 'motion/react';
import { ArrowRight } from 'lucide-react';
import { APP_CONFIG } from '../../config/appConfig';
import { EASE_OUT } from '../../utils/motion';
import { Link } from '../../utils/router';
import { Reveal } from '../common/Reveal';
import { HeroSystemAnimation } from './HeroSystemAnimation';
import { ForecastPreview } from './ForecastPreview';
import { Principles } from './Principles';
import { TrialSiteMap } from './TrialSiteMap';

export function OverviewPage() {
  const reduce = useReducedMotion();
  const rise = (delay: number) => ({
    initial: reduce ? (false as const) : { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.7, ease: EASE_OUT, delay },
  });

  return (
    <>
      {/* On phones the scene leads (people arrive from a QR code); from md up the headline leads. */}
      <section className="relative flex flex-col overflow-x-clip" aria-labelledby="hero-heading">
        <div className="order-2 mx-auto w-full max-w-6xl px-4 pt-1 sm:px-6 md:order-1 md:pt-14 lg:pt-16">
          <motion.h1
            id="hero-heading"
            className="max-w-[16ch] text-[38px] leading-[1.03] font-semibold tracking-[-0.04em] text-balance text-ink sm:text-[58px] lg:max-w-none lg:text-[66px]"
            {...rise(0.05)}
          >
            {APP_CONFIG.tagline}
          </motion.h1>
          <motion.p
            className="mt-3 max-w-[36rem] text-[16px] leading-normal text-pretty text-muted sm:mt-5 sm:text-[19px] sm:leading-relaxed"
            {...rise(0.15)}
          >
            {APP_CONFIG.subtitle}
          </motion.p>
          <motion.div className="mt-5 flex flex-wrap items-center gap-3 sm:mt-8" {...rise(0.25)}>
            <Link
              to="dashboard"
              className="lift group inline-flex items-center gap-2 rounded-full bg-leaf-700 px-5 py-2.5 text-[15px] font-medium text-white shadow-[0_1px_2px_rgb(8_108_76/0.25)] hover:bg-leaf-800 hover:shadow-lift"
            >
              View forecast
              <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
            </Link>
            <Link
              to="methodology"
              className="lift inline-flex items-center rounded-full border border-line-strong bg-surface px-5 py-2.5 text-[15px] font-medium text-ink hover:border-faint hover:shadow-float"
            >
              How it works
            </Link>
          </motion.div>
        </div>
        <div className="order-1 mx-auto w-full max-w-6xl px-1 sm:px-6 md:order-2 md:mt-6">
          <HeroSystemAnimation />
        </div>
        <motion.div className="order-3 mx-auto w-full max-w-6xl px-4 sm:px-6" {...rise(0.32)}>
          <ChallengeScope />
        </motion.div>
      </section>

      <TrialSiteMap />

      <Principles />

      <ForecastPreview />

      <section className="mx-auto max-w-6xl px-4 pb-24 sm:px-6">
        <Reveal className="flex flex-col gap-6 border-t border-line pt-10 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-[22px] font-semibold tracking-[-0.02em] text-ink sm:text-[26px]">See the forecast.</h2>
            <p className="mt-2 max-w-lg text-[15px] leading-relaxed text-muted">
              Start with the yield estimate, then open the methodology when you want the technical detail.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              to="dashboard"
              className="lift inline-flex items-center gap-2 rounded-full bg-leaf-700 px-5 py-2.5 text-[15px] font-medium text-white hover:bg-leaf-800 hover:shadow-lift"
            >
              View forecast
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              to="methodology"
              className="lift inline-flex items-center rounded-full border border-line-strong px-5 py-2.5 text-[15px] font-medium text-ink hover:border-faint"
            >
              How it works
            </Link>
          </div>
        </Reveal>
      </section>
    </>
  );
}

/** What the challenge covers (see backend/data/trial_sites.json). It describes the challenge, not this deployment. */
const SCOPE = ['Maize trial plots', 'Iowa + Nebraska', '2022 season', 'Six-band satellite imagery'];

function ChallengeScope() {
  return (
    <dl className="mt-10 flex max-w-3xl flex-col gap-2 border-t border-line pt-4 sm:flex-row sm:items-baseline sm:gap-5">
      <dt className="shrink-0 text-[11px] font-medium tracking-[0.08em] text-faint uppercase">IoT4Ag challenge scope</dt>
      <dd className="flex flex-wrap gap-x-2 gap-y-1 text-[14px] text-ink-soft">
        {SCOPE.map((item, i) => (
          <span key={item} className="whitespace-nowrap">
            {i > 0 && (
              <span className="mr-2 text-faint" aria-hidden="true">
                ·
              </span>
            )}
            {item}
          </span>
        ))}
      </dd>
    </dl>
  );
}
