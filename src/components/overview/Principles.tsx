import { motion, useReducedMotion } from 'motion/react';
import { EASE_OUT } from '../../utils/motion';

/** The three questions the challenge asks, and what SoilSignal shows for each. */
const QUESTIONS = [
  {
    title: 'Scout where uncertainty is highest',
    body: 'A wide prediction range tells the crew where another field observation may be worth the time.',
  },
  {
    title: 'Measure what imagery adds',
    body: 'Compare field records alone with models that also use the latest satellite pass.',
  },
  {
    title: 'Trade time for accuracy',
    body: 'Earlier forecasts are more useful operationally. Later forecasts usually have more crop signal.',
  },
];

export function Principles() {
  const reduce = useReducedMotion();
  return (
    <section className="mx-auto max-w-6xl px-4 pt-14 pb-20 sm:px-6 sm:pt-20 sm:pb-24" aria-labelledby="questions-heading">
      <h2 id="questions-heading" className="text-[13px] font-medium text-leaf-700">
        What the challenge asks
      </h2>
      <ol className="mt-6 grid gap-10 md:grid-cols-3 md:gap-10">
        {QUESTIONS.map(({ title, body }, i) => (
          <motion.li
            key={title}
            className="border-t border-line pt-6"
            initial={reduce ? false : { opacity: 0, y: 8 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '0px 0px -12% 0px' }}
            transition={{ duration: 0.5, ease: EASE_OUT, delay: i * 0.06 }}
          >
            <span className="data text-[12px] text-faint">{String(i + 1).padStart(2, '0')}</span>
            <h3 className="mt-3 text-[18px] font-semibold tracking-[-0.015em] text-ink">{title}</h3>
            <p className="mt-2 max-w-xs text-[15px] leading-relaxed text-pretty text-muted">{body}</p>
          </motion.li>
        ))}
      </ol>
    </section>
  );
}
