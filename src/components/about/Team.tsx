import { motion, useReducedMotion, type Variants } from 'motion/react';
import { TEAM, type TeamMember } from '../../config/appConfig';
import { EASE_OUT } from '../../utils/motion';
import { PALETTE as C } from '../../utils/palette';

function Member({ member, index }: { member: TeamMember; index: number }) {
  const reduce = useReducedMotion();
  const base = index * 0.08;

  const circle: Variants = {
    hidden: { pathLength: 0, opacity: 0 },
    shown: {
      pathLength: 1,
      opacity: 1,
      transition: { pathLength: { delay: base, duration: 0.75, ease: EASE_OUT }, opacity: { delay: base, duration: 0.05 } },
    },
  };
  const initials: Variants = {
    hidden: { opacity: 0 },
    shown: { opacity: 1, transition: { delay: base + 0.35, duration: 0.4 } },
  };
  const name: Variants = {
    hidden: { opacity: 0, y: 6 },
    shown: { opacity: 1, y: 0, transition: { delay: base + 0.45, duration: 0.5, ease: EASE_OUT } },
  };
  const degree: Variants = {
    hidden: { opacity: 0 },
    shown: { opacity: 1, transition: { delay: base + 0.72, duration: 0.5 } },
  };

  return (
    <motion.li
      className="flex flex-col items-center text-center"
      initial={reduce ? 'shown' : 'hidden'}
      whileInView="shown"
      viewport={{ once: true, margin: '0px 0px -10% 0px' }}
    >
      <div className="relative h-24 w-24">
        <svg viewBox="0 0 96 96" className="absolute inset-0 h-full w-full" aria-hidden="true">
          <circle cx={48} cy={48} r={46} fill={C.surface} opacity={0.8} />
          <motion.circle
            cx={48}
            cy={48}
            r={46}
            fill="none"
            stroke={C.leaf700}
            strokeWidth={1.5}
            strokeLinecap="round"
            transform="rotate(-90 48 48)"
            variants={circle}
          />
        </svg>
        <motion.span
          className="absolute inset-0 flex items-center justify-center text-[24px] font-semibold tracking-[-0.02em] text-leaf-800"
          variants={initials}
          aria-hidden="true"
        >
          {member.initials}
        </motion.span>
      </div>
      <motion.h3 className="mt-5 text-[18px] font-semibold tracking-[-0.015em] text-ink" variants={name}>
        {member.name}
      </motion.h3>
      <motion.p className="mt-1 text-[15px] text-muted" variants={degree} aria-hidden={member.degree ? undefined : true}>
        {member.degree ?? ' '}
      </motion.p>
    </motion.li>
  );
}

/**
 * One column on phones, three per row from `sm` (a short final row stays centered),
 * and the whole team on one row from `lg`. Widths are fixed fractions, so every card
 * is the same size however the rows wrap.
 */
export function Team() {
  return (
    <ul
      className="flex flex-wrap justify-center gap-x-8 gap-y-12 *:w-full sm:*:w-[calc((100%-4rem)/3)] lg:*:w-[calc((100%-8rem)/5)]"
      aria-label="Team"
    >
      {TEAM.map((member, i) => (
        <Member key={member.name} member={member} index={i} />
      ))}
    </ul>
  );
}
