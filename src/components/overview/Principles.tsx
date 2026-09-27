import { motion, useReducedMotion } from 'motion/react';
import { CalendarClock, CloudSun, Plane, Timer } from 'lucide-react';
import { EASE_OUT } from '../../utils/motion';

/** Everything supports the one product: final maize yield, before harvest. */
const SUPPORTING = [
  {
    icon: Timer,
    title: 'How early can we know?',
    body: 'How the forecast error shrinks as the crop develops and new satellite passes arrive.',
  },
  {
    icon: CalendarClock,
    title: 'When will the crop likely mature?',
    body: 'Heat accumulated since planting, and an estimated physiological maturity window.',
  },
  {
    icon: CloudSun,
    title: 'What weather outcomes are plausible?',
    body: 'What the weather did after this date in past seasons at the same location.',
  },
  {
    icon: Plane,
    title: 'Is an extra UAV pass worth it?',
    body: 'Whether adding drone imagery to satellite lowers the forecast error enough to pay for.',
  },
];

export function Principles() {
  const reduce = useReducedMotion();
  return (
    <section className="mx-auto max-w-6xl px-4 pt-14 pb-20 sm:px-6 sm:pt-20 sm:pb-24" aria-labelledby="questions-heading">
      <h2 id="questions-heading" className="text-[13px] font-medium text-leaf-700">
        What SoilSignal answers
      </h2>
      <motion.div
        className="mt-5 rounded-2xl border border-leaf-200 bg-leaf-50/60 p-6 sm:p-8"
        initial={reduce ? false : { opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '0px 0px -10% 0px' }}
        transition={{ duration: 0.5, ease: EASE_OUT }}
      >
        <p className="text-[12px] font-medium tracking-[0.08em] text-leaf-800 uppercase">The product</p>
        <p className="mt-2 text-[26px] leading-tight font-semibold tracking-[-0.025em] text-ink sm:text-[32px]">
          What will this maize field yield at harvest?
        </p>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-soft">
          A final yield forecast in bushels per acre, with a prediction range, updated through the season. The four questions
          below support it.
        </p>
      </motion.div>
      <ol className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {SUPPORTING.map(({ icon: Icon, title, body }, i) => (
          <motion.li
            key={title}
            className="rounded-2xl border border-line bg-surface p-5"
            initial={reduce ? false : { opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '0px 0px -10% 0px' }}
            transition={{ duration: 0.5, ease: EASE_OUT, delay: 0.08 + i * 0.06 }}
          >
            <Icon className="h-5 w-5 text-leaf-700" aria-hidden="true" />
            <h3 className="mt-3 text-[16px] font-semibold tracking-[-0.01em] text-ink">{title}</h3>
            <p className="mt-1.5 text-[14px] leading-relaxed text-muted">{body}</p>
          </motion.li>
        ))}
      </ol>
    </section>
  );
}
